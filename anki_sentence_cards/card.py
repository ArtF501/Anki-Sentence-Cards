"""Assemble a card draft from the chosen sentence and the four sources.

Each source runs in its own try/except SourceError: a dead source leaves its
field empty, records why, and never stops the card or the batch.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .book.search import Occurrence, mark_match
from .settings import Settings
from .sources import dictionary, meaning, translate, tts
from .sources.http import SourceError

log = logging.getLogger(__name__)


@dataclass
class CardDraft:
    word: str
    values: Dict[str, str]
    audio: Optional[bytes] = None
    audio_name: str = ""
    missing: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)  # batch-level notices


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

    definition = ""
    if len(word.split()) > 1:
        d.values["pos"] = "phrase"
    else:
        def do_lookup():
            data = dictionary.lookup(word)
            if data is None or not getattr(data, "roles", None):
                raise SourceError("словарь ничего не вернул")
            role = data.roles[0]
            pos = (role.pos or "").strip()
            ipa = (role.ipa or data.shared_ipa or "").strip()
            if pos:
                d.values["pos"] = pos
            else:
                _fail(d, ["pos"], "часть речи", "словарь не дал часть речи")
            if ipa:
                d.values["ipa"] = ipa
            else:
                _fail(d, ["ipa"], "транскрипция", "словарь не дал транскрипцию")
            return (role.definition or "").strip()

        definition = _guard(d, ["pos", "ipa"], "словарь", do_lookup) or ""

    def do_meaning():
        options = meaning.get_meaning_options(word, settings.deepl_key)
        if not options or not (options[0].translation or "").strip():
            raise SourceError("значение пустое")
        option = options[0]
        hint = option.hint or meaning.fallback_hint(definition)
        d.values["meaning"] = meaning.compose(hint, definition, option.translation.strip())

    _guard(d, ["meaning"], "значение слова", do_meaning)

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
