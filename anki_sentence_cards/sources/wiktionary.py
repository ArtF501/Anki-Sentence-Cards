"""Fallback dictionary: parts of speech and definitions from Wiktionary's REST.

The primary dictionary (dictionaryapi.dev) goes down word by word, and a word
it refuses must still get a card. This source answers the same WordData shape
and never guesses a transcription: that is task of lookup_ipa below.
"""
from __future__ import annotations

import html
import re
from urllib.parse import quote

from . import http
from .http import SourceError
from .roles import Role, WordData, merge_roles

DEFINITION_URL = "https://en.wiktionary.org/api/rest_v1/page/definition/"
SOURCE = "wiktionary"
_TAG = re.compile(r"<[^>]*>")


def strip_markup(html_text: str) -> str:
    """Definition text without tags, entities or runs of whitespace."""
    if not isinstance(html_text, str):
        return ""
    return " ".join(html.unescape(_TAG.sub(" ", html_text)).split())


def parse_definitions(payload) -> WordData:
    """The English section of a REST definition response -> WordData.

    Only the "en" key is read: the same page carries French and Latin entries
    whose parts of speech are not even in English.
    """
    if not isinstance(payload, dict):
        raise SourceError("Wiktionary вернул непонятный ответ")
    sections = payload.get("en")
    if not isinstance(sections, list) or not sections:
        raise SourceError("Wiktionary не знает это слово по-английски")
    roles = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        pos = strip_markup(section.get("partOfSpeech", "")).lower()
        if not pos:
            continue
        defs = section.get("definitions")
        definition = ""
        if isinstance(defs, list):
            for d in defs:
                if isinstance(d, dict):
                    definition = strip_markup(d.get("definition", ""))
                    if definition:
                        break
        roles.append(Role(pos, "", definition, "", SOURCE))
    if not roles:
        raise SourceError("Wiktionary вернул неполный ответ")
    return WordData(merge_roles(roles), "")


def lookup(word: str) -> WordData:
    word = (word or "").strip()
    if not word:
        raise SourceError("пустое слово")
    if len(word.split()) != 1:
        raise SourceError("Wiktionary работает только с одним словом")
    return parse_definitions(http.get_json(DEFINITION_URL + quote(word, safe="")))
