"""Assemble a card draft from the chosen sentence and the four sources.

Each source runs in its own try/except SourceError: a dead source leaves its
field empty, records why, and never stops the card or the batch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .book.search import Occurrence, mark_match
from .settings import Settings
from .sources import dictionary, meaning, translate, tts
from .sources.http import SourceError


@dataclass
class CardDraft:
    word: str
    values: Dict[str, str]
    audio: Optional[bytes] = None
    audio_name: str = ""
    missing: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _fail(draft: CardDraft, key: str, label: str, reason: str) -> None:
    if key not in draft.missing:
        draft.missing.append(key)
    draft.errors.append("%s: %s" % (label, reason))


def build_draft(word: str, occ: Occurrence, settings: Settings) -> CardDraft:
    d = CardDraft(
        word=word,
        values={k: "" for k in ("front", "translate", "pos", "ipa", "meaning", "sound")},
    )
    d.values["front"] = mark_match(occ)

    try:
        tr = translate.translate(occ.sentence, settings.deepl_key)
        if not (tr.text or "").strip():
            raise SourceError("переводчик вернул пустой ответ")
        d.values["translate"] = tr.text.strip()
    except SourceError as e:
        _fail(d, "translate", "перевод предложения", str(e))

    entry = None
    if len(word.split()) > 1:
        d.values["pos"] = "phrase"
    else:
        try:
            entry = dictionary.lookup(word)
            d.values["pos"] = entry.part_of_speech
            if entry.ipa:
                d.values["ipa"] = entry.ipa
            else:
                _fail(d, "ipa", "транскрипция", "словарь не дал транскрипцию")
        except SourceError as e:
            _fail(d, "pos", "словарь", str(e))
            _fail(d, "ipa", "словарь", str(e))

    try:
        m = meaning.get_meaning(word, settings.deepl_key, entry)
        if not (m.text or "").strip():
            raise SourceError("значение пустое")
        d.values["meaning"] = m.text
    except SourceError as e:
        _fail(d, "meaning", "значение слова", str(e))

    try:
        data = tts.synthesize(word, settings.tts_lang)
        if not data:
            raise SourceError("сервис озвучки вернул пустой ответ")
        d.audio = data
        d.audio_name = tts.media_name(word, data)
        d.values["sound"] = "[sound:%s]" % d.audio_name
    except SourceError as e:
        _fail(d, "sound", "озвучка слова", str(e))

    return d
