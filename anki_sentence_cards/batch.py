"""Pure logic of the main window: word list, picking state, batch, report.

No Qt/Anki imports: the dialog calls exactly these functions, and the tests
call them too. Error handling follows the contract of notes.py.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .book.search import Occurrence, find_occurrences
from .notes import DuplicateCheckFailed, NoteError, NoteTypeMissing, resolve_field_map

CREATED = "created"
INCOMPLETE = "incomplete"
DUPLICATE = "duplicate"
FAILED = "failed"
NOT_PROCESSED = "not_processed"


def parse_words(text: str) -> List[str]:
    """One word or phrase per line; empty lines and repeats (any case) dropped."""
    seen = set()
    out: List[str] = []
    for line in text.splitlines():
        w = " ".join(line.split())
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


def manual_occurrence(word: str, sentence: str) -> Occurrence:
    """Occurrence for a hand-typed sentence; the word is bolded if it occurs."""
    sentence = " ".join(sentence.split())
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


def build_drafts(picks: List[Pick], build: Callable, progress: Callable[[int, int, str], None] = None):
    """Background thread: (pick, draft or None, error or '') for each pick."""
    out = []
    for i, p in enumerate(picks):
        if progress:
            progress(i, len(picks), p.word)
        try:
            out.append((p, build(p.word, p.occ), ""))
        except Exception as e:  # build_draft should not raise; safety net
            out.append((p, None, "не удалось собрать карточку: %s" % e))
    return out


def add_all(built, add: Callable, result: BatchResult) -> None:
    """Main thread: write notes. NoteTypeMissing stops the batch."""
    for n, (p, draft, err) in enumerate(built):
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
