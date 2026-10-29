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
from .roles import Role, WordData, merge_roles, normalize_pos

DEFINITION_URL = "https://en.wiktionary.org/api/rest_v1/page/definition/"
WIKITEXT_URL = "https://en.wiktionary.org/w/api.php"
SOURCE = "wiktionary"
_TAG = re.compile(r"<[^>]*>")
_IPA_TEMPLATE = re.compile(r"\{\{IPA\|en\|([^}]*)\}\}")
_WRAPPED = re.compile(r"^(?:/(.+)/|\[(.+)\])$")
_BRITISH = ("rp", "uk")


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
        pos = normalize_pos(strip_markup(section.get("partOfSpeech", "")))
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


def parse_ipa(wikitext: str) -> str:
    """British transcription out of the page's {{IPA}} templates, or "".

    A best effort over markup nobody promised us: anything not recognised
    gives an empty string, never a half-read guess and never an exception.
    """
    if not isinstance(wikitext, str):
        return ""
    first = ""
    for match in _IPA_TEMPLATE.finditer(wikitext):
        parts = match.group(1).split("|")
        accents = ",".join(p.split("=", 1)[1] for p in parts if p.startswith("a=")).lower()
        values = []
        for part in parts:
            wrapped = _WRAPPED.match(part.strip())
            if wrapped:
                values.append((wrapped.group(1) or wrapped.group(2)).strip())
        values = [v for v in values if v]
        if not values:
            continue
        if any(a in accents for a in _BRITISH):
            return values[0]
        if not first:
            first = values[0]
    return first


def lookup_ipa(word: str) -> str:
    """Transcription from the page's own markup; "" when it is not there.

    The REST definition endpoint carries no transcription at all, so this is
    a second request against a different entry point. It is allowed to come
    back empty: a card without a transcription is still a card.
    """
    word = (word or "").strip()
    if not word or len(word.split()) != 1:
        return ""
    payload = http.get_json(WIKITEXT_URL, params={
        "action": "parse", "page": word, "prop": "wikitext",
        "format": "json", "formatversion": "2",
    })
    if not isinstance(payload, dict):
        return ""
    parse = payload.get("parse")
    if not isinstance(parse, dict):
        return ""
    wikitext = parse.get("wikitext")
    if isinstance(wikitext, dict):           # formatversion 1 shape
        wikitext = wikitext.get("*")
    return parse_ipa(wikitext)
