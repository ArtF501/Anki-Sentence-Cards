"""Pure logic of the main window: word list, picking state, batch, report.

No Qt/Anki imports: the dialog calls exactly these functions, and the tests
call them too. Error handling follows the contract of notes.py.
"""
from __future__ import annotations

import html
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .book.normalize import normalize_query
from .book.search import Occurrence, find_occurrences
from .card import CardDraft, chosen_role, resolve_choices
from .notes import DuplicateCheckFailed, NoteError, NoteTypeMissing, resolve_field_map
from .sources.meaning import compose, fallback_hint
from .sources.roles import Role

CREATED = "created"
INCOMPLETE = "incomplete"
DUPLICATE = "duplicate"
FAILED = "failed"
NOT_PROCESSED = "not_processed"

MAX_WORKERS = 8
STOPPED = "перерыв прерван"


_LEAD = re.compile(r"^\(?\d+[.)]\s+|^[-*\u2022]\s+")
_EDGE_PUNCT = ",.;:!?\"“”«»()[]"


def parse_words(text: str) -> List[str]:
    """One word or phrase per line; empty lines and repeats (any case) dropped."""
    seen = set()
    out: List[str] = []
    for line in text.splitlines():
        w = " ".join(line.split())
        w = _LEAD.sub("", w)
        w = w.strip(_EDGE_PUNCT).strip()
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


def manual_occurrence(word: str, sentence: str) -> Occurrence:
    """Occurrence for a hand-typed sentence; the word is bolded if it occurs."""
    sentence = normalize_query(" ".join(sentence.split()))
    found, _ = find_occurrences([sentence], word, 1)
    if found:
        return found[0]
    return Occurrence(0, sentence, "", 0, 0, False)


def highlight_html(occ: Occurrence) -> str:
    """Sentence as safe HTML with the matched form in <b>."""
    s = occ.sentence
    if occ.start == occ.end:
        return html.escape(s)
    return (html.escape(s[: occ.start]) + "<b>" + html.escape(s[occ.start : occ.end])
            + "</b>" + html.escape(s[occ.end :]))


def limit_note(shown: int, truncated: bool, limit: int) -> str:
    """Line under the list; '' when everything is shown."""
    if not truncated:
        return ""
    return "показаны первые %d (лимит в настройках: %d), в книге есть ещё" % (shown, limit)


@dataclass
class Pick:
    word: str
    occ: Occurrence


class PickState:
    """Walks the words one by one; every choice is an explicit user action."""

    def __init__(self, words: List[str]):
        self.words = list(words)
        self.index = 0
        self.picks: List[Pick] = []
        self.skipped: List[str] = []

    @property
    def done(self) -> bool:
        return self.index >= len(self.words)

    @property
    def current(self) -> Optional[str]:
        return None if self.done else self.words[self.index]

    @property
    def counter(self) -> str:
        return "%d из %d" % (min(self.index + 1, len(self.words)), len(self.words))

    def choose(self, occ: Occurrence) -> None:
        if not self.done:
            self.picks.append(Pick(self.words[self.index], occ))
            self.index += 1

    def skip(self) -> None:
        if not self.done:
            self.skipped.append(self.words[self.index])
            self.index += 1

    def choose_manual(self, sentence: str) -> bool:
        """False (and nothing happens) for an empty sentence."""
        if self.done or not sentence.strip():
            return False
        self.choose(manual_occurrence(self.words[self.index], sentence))
        return True


def needs_choice(draft: CardDraft) -> bool:
    """True when there is an actual choice to make: one variant is no choice."""
    return len(draft.roles) > 1 or len(draft.meanings) > 1


def role_label(role: Role, shared_ipa: str = "") -> str:
    """Button text for one role: part of speech, transcription, base-form mark."""
    parts = [role.pos or "?"]
    ipa = (role.ipa or shared_ipa or "").strip()
    if ipa:
        parts.append(ipa)
    if role.lemma:
        parts.append("(от %s)" % role.lemma)
    return "  ".join(parts)


def meaning_labels(draft: CardDraft) -> List[str]:
    """Candidate meanings exactly as they would land in the field.

    The English part comes from the role chosen right now, so the list is
    redrawn whenever the role changes.
    """
    role = chosen_role(draft)
    definition = (role.definition or "").strip() if role else ""
    out = []
    for option in draft.meanings:
        hint = option.hint or fallback_hint(definition)
        out.append(compose(hint, definition, option.translation.strip()))
    return out


class ChoiceState:
    """Walks the drafts that have something to choose, in the batch's order.

    Mutates the very drafts it was given: the caller writes its notes from the
    same objects afterwards, with the user's choices already in their fields.
    """

    def __init__(self, drafts: List[CardDraft]):
        self.drafts = list(drafts)
        self.index = 0
        self._settle()

    def _settle(self) -> None:
        """Resolve and pass over every draft with nothing to ask."""
        while self.index < len(self.drafts) and not needs_choice(self.drafts[self.index]):
            resolve_choices(self.drafts[self.index])
            self.index += 1

    @property
    def done(self) -> bool:
        return self.index >= len(self.drafts)

    @property
    def current(self) -> Optional[CardDraft]:
        return None if self.done else self.drafts[self.index]

    @property
    def counter(self) -> str:
        return "%d из %d" % (min(self.index + 1, len(self.drafts)), len(self.drafts))

    def needs_role(self) -> bool:
        return not self.done and len(self.current.roles) > 1

    def needs_meaning(self) -> bool:
        return not self.done and len(self.current.meanings) > 1

    def role_labels(self) -> List[str]:
        d = self.current
        return [] if d is None else [role_label(r, d.shared_ipa) for r in d.roles]

    def meaning_labels(self) -> List[str]:
        d = self.current
        return [] if d is None else meaning_labels(d)

    def choose_role(self, i: int) -> None:
        """The cursor stays: the meanings are redrawn under the new role."""
        d = self.current
        if d is not None and 0 <= i < len(d.roles):
            d.role_index = i

    def choose_meaning(self, i: int) -> None:
        """Take this meaning and move on. With no meanings at all, i=0 confirms."""
        d = self.current
        if d is None:
            return
        if d.meanings:
            if not 0 <= i < len(d.meanings):
                return
            d.meaning_index = i
        elif i != 0:
            return
        resolve_choices(d)
        self.index += 1
        self._settle()

    def accept_all(self) -> None:
        """Everything left keeps the variants it has now; nothing is asked again."""
        while not self.done:
            resolve_choices(self.drafts[self.index])
            self.index += 1


@dataclass
class Preflight:
    field_map: Dict[str, str]
    fatal: str = ""
    warnings: List[str] = field(default_factory=list)


def preflight(settings, notetype_fields: Optional[List[str]], book_exists: bool) -> Preflight:
    """Checks done once before the batch. `notetype_fields` None = no such type."""
    if not settings.active_book or not book_exists:
        return Preflight({}, "Не выбрана книга или файл книги не найден (Настройки).")
    if not settings.deck:
        return Preflight({}, "Не выбрана колода (Настройки).")
    if notetype_fields is None:
        return Preflight({}, "Тип заметки «%s» не найден (Настройки)." % settings.notetype)
    fmap, unresolved = resolve_field_map(notetype_fields, settings.field_map)
    if "front" in unresolved:
        return Preflight({}, "Поле front не сопоставлено (Настройки, «Сопоставить поля вручную»).")
    warns = []
    if unresolved:
        warns.append("Не сопоставлены поля: %s. Они останутся пустыми." % ", ".join(unresolved))
    return Preflight(fmap, "", warns)


@dataclass
class Outcome:
    word: str
    status: str
    reasons: List[str] = field(default_factory=list)


@dataclass
class BatchResult:
    outcomes: List[Outcome] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _reason(e: Exception) -> str:
    return str(e) if isinstance(e, NoteError) else "внутренняя ошибка: %s" % e


def split_duplicates(picks: List[Pick], find_dup: Callable[[str], Optional[int]],
                     result: BatchResult) -> List[Pick]:
    """Main thread, before building: picks that are not duplicates.

    Duplicates go to result as DUPLICATE. DuplicateCheckFailed: one warning,
    checking is off for the rest, the word is NOT failed.
    """
    check = True
    rest: List[Pick] = []
    for p in picks:
        if check:
            try:
                if find_dup(p.word) is not None:
                    result.outcomes.append(Outcome(p.word, DUPLICATE, ["уже есть"]))
                    continue
            except DuplicateCheckFailed as e:
                result.warnings.append("%s. Проверка дубликатов отключена до конца партии." % e)
                check = False
            except Exception as e:
                result.outcomes.append(Outcome(p.word, FAILED, [_reason(e)]))
                continue
        rest.append(p)
    return rest


def build_drafts(picks: List[Pick], build: Callable,
                 progress: Callable[[int, int, str], None] = None,
                 workers: int = 6,
                 should_stop: Optional[Callable[[], bool]] = None):
    """Background thread: (pick, draft or None, error or '') for each pick.

    The words are fetched in parallel — twenty of them one by one would be a
    quarter of an hour of waiting — but the result keeps the order of `picks`,
    because the user picked the sentences in that order and will choose roles
    in it too. `should_stop` is read before each word: whoever asked to stop
    gets back everything already built and an honest reason for the rest.
    """
    total = len(picks)
    if not total:
        return []
    out: List[Optional[Tuple]] = [None] * total
    lock = threading.Lock()
    counter = {"done": 0}

    def one(i: int, p: Pick) -> None:
        if should_stop is not None and should_stop():
            out[i] = (p, None, STOPPED)
        else:
            try:
                out[i] = (p, build(p.word, p.occ), "")
            except Exception as e:  # build_draft should not raise; safety net
                out[i] = (p, None, "не удалось собрать карточку: %s" % e)
        if progress:
            with lock:
                done_before = counter["done"]
                counter["done"] += 1
            progress(done_before, total, p.word)

    with ThreadPoolExecutor(max_workers=max(1, min(int(workers or 1), total))) as pool:
        for i, p in enumerate(picks):
            pool.submit(one, i, p)
    for i, slot in enumerate(out):
        if slot is None:  # a worker died before it could write its slot
            out[i] = (picks[i], None, "не удалось собрать карточку")
    return out


def add_all(built, add: Callable, result: BatchResult) -> None:
    """Main thread: write notes. NoteTypeMissing stops the batch."""
    for n, (p, draft, err) in enumerate(built):
        if draft is not None:
            for w in draft.warnings:
                if w not in result.warnings:
                    result.warnings.append(w)
        if draft is None:
            result.outcomes.append(Outcome(p.word, FAILED, [err]))
            continue
        try:
            add(draft)
        except NoteTypeMissing as e:
            result.outcomes.append(Outcome(p.word, NOT_PROCESSED, [str(e)]))
            for p2, _, _ in built[n + 1:]:
                result.outcomes.append(Outcome(p2.word, NOT_PROCESSED, ["партия остановлена: %s" % e]))
            result.warnings.append("Партия остановлена: %s" % e)
            return
        except Exception as e:  # NoteError and the safety net: same handling
            result.outcomes.append(Outcome(p.word, FAILED, [_reason(e)]))
            continue
        if draft.missing:
            result.outcomes.append(Outcome(p.word, INCOMPLETE, list(draft.errors)))
        else:
            result.outcomes.append(Outcome(p.word, CREATED))


def run_batch(picks: List[Pick], find_dup: Callable, build: Callable, add: Callable,
              result: BatchResult, run_bg: Callable, done: Callable[[BatchResult], None],
              progress: Callable = None,
              choose: Optional[Callable[[List[Tuple], Callable[[], None]], None]] = None,
              workers: int = 6,
              should_stop: Optional[Callable[[], bool]] = None) -> None:
    """The whole sequence; the dialog and the tests both call exactly this.

    split_duplicates (main) -> build_drafts via run_bg (background) ->
    choose (main, optional) -> add_all (main) -> done(result).
    `run_bg(work, ok, fail)` runs work() off the main thread and calls
    ok(value) or fail(exc) back on it; tests pass a synchronous one. `choose`
    gets the built drafts and the closure that finishes the batch: nothing is
    written and no report is shown until it calls that closure. If the
    background step fails, the picks that were to be built become
    NOT_PROCESSED (retryable).
    """
    rest = split_duplicates(picks, find_dup, result)
    if not rest:
        done(result)
        return

    def finish(built):
        add_all(built, add, result)
        done(result)

    def ok(built):
        if choose is None:
            finish(built)
            return
        choose(built, lambda: finish(built))

    def fail(e):
        result.warnings.append("Сборка карточек прервана: %s" % e)
        for p in rest:
            result.outcomes.append(Outcome(p.word, NOT_PROCESSED, ["сборка прервана: %s" % e]))
        done(result)

    run_bg(lambda: build_drafts(rest, build, progress, workers, should_stop), ok, fail)


def merge_results(prev: BatchResult, new: BatchResult, retried: List[str]) -> BatchResult:
    """After a retry: earlier outcomes stay, except for the retried words."""
    again = set(retried)
    return BatchResult(
        [o for o in prev.outcomes if o.word not in again] + new.outcomes,
        prev.warnings + new.warnings,
    )


def group_report(outcomes: List[Outcome]) -> Dict[str, List[Outcome]]:
    return {
        "created": [o for o in outcomes if o.status == CREATED],
        "incomplete": [o for o in outcomes if o.status == INCOMPLETE],
        "not_created": [o for o in outcomes if o.status in (DUPLICATE, FAILED, NOT_PROCESSED)],
    }


def retry_words(outcomes: List[Outcome]) -> List[str]:
    """Words worth another go: failed or not processed. Not duplicates (the
    card exists) and not incomplete ones (the card was created)."""
    return [o.word for o in outcomes if o.status in (FAILED, NOT_PROCESSED)]


def report_text(outcomes: List[Outcome]) -> List[Tuple[str, List[str]]]:
    """(group title, lines) for the non-empty groups."""
    g = group_report(outcomes)
    titles = [("created", "Создано"), ("incomplete", "Создано с пустыми полями"),
              ("not_created", "Не создано")]
    res = []
    for key, title in titles:
        if g[key]:
            lines = [o.word + (" — " + "; ".join(o.reasons) if o.reasons else "") for o in g[key]]
            res.append(("%s (%d)" % (title, len(g[key])), lines))
    return res
