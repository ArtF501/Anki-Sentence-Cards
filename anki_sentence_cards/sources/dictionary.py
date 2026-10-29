"""Every role of a word from dictionaryapi.dev, with transcriptions tied to it."""
from __future__ import annotations

from urllib.parse import quote

from . import http
from .http import SourceError
from .roles import Role, WordData, merge_roles, normalize_pos

URL = "https://api.dictionaryapi.dev/api/v2/entries/en/"
SOURCE = "dictionaryapi"


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


def _entry_roles(entry: dict) -> list:
    meanings = entry.get("meanings")
    if not isinstance(meanings, list) or not meanings:
        raise SourceError("словарь вернул непонятный ответ")
    roles = []
    for meaning in meanings:
        if not isinstance(meaning, dict):
            raise SourceError("словарь вернул непонятный ответ")
        pos = normalize_pos(_text(meaning.get("partOfSpeech")))
        defs = meaning.get("definitions", [])
        if not isinstance(defs, list) or (defs and not isinstance(defs[0], dict)):
            raise SourceError("словарь вернул непонятный ответ")
        if not pos:
            raise SourceError("словарь вернул неполный ответ")
        definition = _text(defs[0].get("definition")) if defs else ""
        roles.append(Role(pos, "", definition, "", SOURCE))
    return roles


def parse_entries(payload) -> WordData:
    """All roles of the word, with the transcription pairing rule applied.

    An entry's transcription belongs to a role only when the entry holds
    exactly one role. Otherwise nothing says which of its roles the
    transcription is for, so it becomes the word's shared transcription.
    """
    if not isinstance(payload, list) or not payload:
        raise SourceError("словарь вернул непонятный ответ")
    roles = []
    shared = ""
    for entry in payload:
        if not isinstance(entry, dict):
            raise SourceError("словарь вернул непонятный ответ")
        found = _entry_roles(entry)
        ipa = _ipa(entry)
        if len(found) == 1:
            found[0].ipa = ipa
        elif ipa and not shared:
            shared = ipa
        roles += found
    if not roles:
        raise SourceError("словарь вернул неполный ответ")
    return WordData(merge_roles(roles), shared)


def lookup(word: str) -> WordData:
    word = (word or "").strip()
    if not word:
        raise SourceError("пустое слово")
    if len(word.split()) != 1:
        raise SourceError("словарь работает только с одним словом")
    return parse_entries(http.get_json(URL + quote(word, safe="")))
