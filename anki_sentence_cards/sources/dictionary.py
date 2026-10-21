"""Part of speech and IPA from dictionaryapi.dev (first, primary variant)."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from . import http
from .http import SourceError

URL = "https://api.dictionaryapi.dev/api/v2/entries/en/"


@dataclass
class DictEntry:
    part_of_speech: str
    ipa: str
    definition: str


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _ipa(entry: dict) -> str:
    phonetics = entry.get("phonetics", [])
    if not isinstance(phonetics, list):
        raise SourceError("словарь вернул непонятный ответ")
    candidates = [entry.get("phonetic")]
    candidates += [p.get("text") for p in phonetics if isinstance(p, dict)]
    for c in candidates:
        ipa = _text(c).strip("/").strip()
        if ipa:
            return ipa
    return ""  # no transcription: the field stays empty, the card is still made


def parse_entry(payload) -> DictEntry:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise SourceError("словарь вернул непонятный ответ")
    entry = payload[0]
    meanings = entry.get("meanings")
    if not isinstance(meanings, list) or not meanings or not isinstance(meanings[0], dict):
        raise SourceError("словарь вернул непонятный ответ")
    meaning = meanings[0]
    pos = _text(meaning.get("partOfSpeech")).lower()
    defs = meaning.get("definitions")
    if not isinstance(defs, list) or not defs or not isinstance(defs[0], dict):
        raise SourceError("словарь вернул непонятный ответ")
    definition = _text(defs[0].get("definition"))
    if not pos or not definition:
        raise SourceError("словарь вернул неполный ответ")
    return DictEntry(pos, _ipa(entry), definition)


def lookup(word: str) -> DictEntry:
    word = (word or "").strip()
    if not word:
        raise SourceError("пустое слово")
    if len(word.split()) != 1:
        raise SourceError("словарь работает только с одним словом")
    return parse_entry(http.get_json(URL + quote(word, safe="")))
