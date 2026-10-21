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


def build_draft(word: str, occ: Occurrence, settings: Settings) -> CardDraft:
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

    _guard(d, ["translate"], "перевод предложения", do_translate)

    entry = None
    if len(word.split()) > 1:
        d.values["pos"] = "phrase"
    else:
        def do_lookup():
            e = dictionary.lookup(word)
            if e is None:
                raise SourceError("словарь ничего не вернул")
            pos = (e.part_of_speech or "").strip()
            ipa = (e.ipa or "").strip()
            if pos:
                d.values["pos"] = e.part_of_speech
            else:
                _fail(d, ["pos"], "часть речи", "словарь не дал часть речи")
            if ipa:
                d.values["ipa"] = e.ipa
            else:
                _fail(d, ["ipa"], "транскрипция", "словарь не дал транскрипцию")
            return e

        entry = _guard(d, ["pos", "ipa"], "словарь", do_lookup)

    def do_meaning():
        m = meaning.get_meaning(word, settings.deepl_key, entry)
        if not (m.text or "").strip():
            raise SourceError("значение пустое")
        d.values["meaning"] = m.text

    _guard(d, ["meaning"], "значение слова", do_meaning)

    def do_sound():
        data = tts.synthesize(word, settings.tts_lang)
        if not data:
            raise SourceError("сервис озвучки вернул пустой ответ")
        name = tts.media_name(word, data)
        d.audio, d.audio_name = data, name
        d.values["sound"] = "[sound:%s]" % name

    _guard(d, ["sound"], "озвучка слова", do_sound)
    return d
