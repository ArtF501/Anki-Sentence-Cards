"""Assemble a card draft from the chosen sentence and the sources.

Each source runs in its own try/except SourceError: a dead source leaves its
field empty, records why, and never stops the card or the batch.

The draft is built in two steps on purpose. `build_draft` only gathers: it
puts every role and every candidate meaning into the draft and fills no field
that depends on them, because which role the word plays is decided by reading
the sentence, and only the user is reading it. `resolve_choices` turns the
indexes the user picked into the three fields.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .book.search import Occurrence, mark_match
from .settings import Settings
from .sources import meaning, translate, tts, words
from .sources.http import SourceError
from .sources.meaning import MeaningOption
from .sources.roles import Role

log = logging.getLogger(__name__)

CHOSEN_KEYS = ("pos", "ipa", "meaning")


@dataclass
class CardDraft:
    word: str
    values: Dict[str, str]
    audio: Optional[bytes] = None
    audio_name: str = ""
    missing: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)  # batch-level notices
    roles: List[Role] = field(default_factory=list)
    shared_ipa: str = ""
    meanings: List[MeaningOption] = field(default_factory=list)
    role_index: int = 0
    meaning_index: int = 0


def _fail(draft: CardDraft, keys, label: str, reason: str) -> None:
    for key in keys:
        if key not in draft.missing:
            draft.missing.append(key)
    draft.errors.append("%s: %s" % (label, reason))


def _guard(draft: CardDraft, keys, label: str, fn):
    """Run one source. Any failure (even a non-SourceError bug) is isolated."""
    try:
        return fn()
    except SourceError as e:
        _fail(draft, keys, label, str(e))
    except Exception:
        log.exception("card source %r failed for word %r", label, draft.word)
        _fail(draft, keys, label, "внутренняя ошибка")
    return None


def _is_phrase(word: str) -> bool:
    return len((word or "").split()) > 1


def _pick(items: List, index: int):
    if not items:
        return None
    return items[index] if 0 <= index < len(items) else items[0]


def chosen_role(draft: CardDraft) -> Optional[Role]:
    return _pick(draft.roles, draft.role_index)


def resolve_choices(draft: CardDraft) -> None:
    """Write pos/ipa/meaning from the chosen role and meaning.

    Safe to call again after the user changes a choice: every field is written
    from scratch and its `missing` mark is set or cleared to match.
    """
    role = chosen_role(draft)
    definition = (role.definition or "").strip() if role else ""
    draft.values["pos"] = (role.pos or "").strip() if role else ""
    draft.values["ipa"] = ((role.ipa or draft.shared_ipa) or "").strip() if role else ""
    option = _pick(draft.meanings, draft.meaning_index)
    if option is None:
        draft.values["meaning"] = ""
    else:
        hint = option.hint or meaning.fallback_hint(definition)
        draft.values["meaning"] = meaning.compose(hint, definition,
                                                  option.translation.strip())
    # a phrase has no transcription by design: that is not a missing field
    keys = [k for k in CHOSEN_KEYS if not (k == "ipa" and _is_phrase(draft.word))]
    for key in keys:
        if draft.values[key]:
            if key in draft.missing:
                draft.missing.remove(key)
        elif key not in draft.missing:
            draft.missing.append(key)


def build_draft(word: str, occ: Occurrence, settings: Settings,
                want_sound: bool = True) -> CardDraft:
    d = CardDraft(
        word=word,
        values={k: "" for k in ("front", "translate", "pos", "ipa", "meaning", "sound")},
    )
    d.values["front"] = mark_match(occ)

    def do_translate():
        tr = translate.translate(occ.sentence, settings.deepl_key)
        if not (tr.text or "").strip():
            raise SourceError("переводчик вернул пустой ответ")
        d.values["translate"] = tr.text.strip()
        if tr.note and tr.note not in d.warnings:
            d.warnings.append(tr.note)

    _guard(d, ["translate"], "перевод предложения", do_translate)

    if _is_phrase(word):
        d.roles = [Role("phrase")]
    else:
        def do_roles():
            data = words.fetch_word_data(word, settings)
            if data is None or not getattr(data, "roles", None):
                raise SourceError("ни один словарь не ответил")
            d.roles = list(data.roles)
            d.shared_ipa = (data.shared_ipa or "").strip()

        _guard(d, [], "словарь", do_roles)

    def do_meanings():
        options = meaning.get_meaning_options(word, settings.deepl_key)
        usable = [o for o in (options or []) if (o.translation or "").strip()]
        if not usable:
            raise SourceError("значение пустое")
        d.meanings = usable

    _guard(d, [], "значение слова", do_meanings)

    def do_sound():
        data = tts.synthesize(word, settings.tts_lang)
        if not data:
            raise SourceError("сервис озвучки вернул пустой ответ")
        name = tts.media_name(word, data)
        d.audio, d.audio_name = data, name
        d.values["sound"] = "[sound:%s]" % name

    if want_sound:
        _guard(d, ["sound"], "озвучка слова", do_sound)
    return d
