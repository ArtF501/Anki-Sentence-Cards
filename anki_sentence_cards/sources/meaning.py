"""Word meaning field: "(hint) English definition - Russian translation".

Primary: Reverso Context page (HTML, no official API, layout may change).
Fallback: dictionary definition + translator, same shape.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional, Tuple
from urllib.parse import quote

from . import http, translate
from .dictionary import DictEntry
from .http import SourceError

URL = "https://context.reverso.net/translation/english-russian/"
_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
_BAD = re.compile(r"[<>{}\d]")
_STOP = {"a", "an", "the", "to", "or", "and", "of", "in", "on", "for", "with",
         "that", "which", "who", "is", "being", "by", "as", "at", "from"}


@dataclass
class Meaning:
    text: str
    source: str


def _plausible(text: str) -> bool:
    """Shared sanity check for a Russian translation, whichever source gave it."""
    return bool(_CYRILLIC.search(text)) and not _BAD.search(text) and len(text) <= 60


class _Reverso(HTMLParser):
    """Collects the first term (and hint) of the first translation anchor."""

    def __init__(self):
        super().__init__()
        self.depth_content = 0
        self.in_anchor = False
        self.done = False
        self.field = None      # "term" / "hint" while inside that span
        self.span_depth = 0    # nesting inside the current field span
        self.term_done = False
        self.broken = False
        self.hint_done = False
        self.term = ""
        self.hint = ""

    def _abort(self):
        """Anchor boundary reached while a field span is still open: broken markup."""
        self.broken = True
        self.done = True

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "div" and (a.get("id") == "translations-content" or self.depth_content):
            self.depth_content += 1
        if not self.depth_content or self.done:
            return
        if self.field:
            if tag == "a" and "translation" in classes:
                self._abort()
            elif tag == "span":
                self.span_depth += 1
        elif tag == "a" and "translation" in classes:
            if self.in_anchor:  # previous anchor never closed
                self.done = True
            self.in_anchor = True
        elif self.in_anchor and tag == "span":
            if "display-term" in classes and not self.term_done:
                self.field, self.span_depth = "term", 1
            elif "context-hint" in classes and not self.hint_done:
                self.field, self.span_depth = "hint", 1

    def handle_endtag(self, tag):
        if tag == "span" and self.field:
            self.span_depth -= 1
            if self.span_depth == 0:
                if self.field == "term":
                    self.term_done = True
                else:
                    self.hint_done = True
                self.field = None
        elif tag == "a" and self.in_anchor:
            if self.field:
                self._abort()
            self.in_anchor = False
            self.done = True
        elif tag == "div" and self.depth_content:
            self.depth_content -= 1

    def handle_data(self, data):
        if self.in_anchor and not self.done:
            if self.field == "term":
                self.term += data
            elif self.field == "hint":
                self.hint += data


def _parse_reverso(html: bytes) -> Tuple[str, str]:
    """Reverso page -> (hint, translation); hint may be empty.

    The only place that knows Reverso's layout. Raises SourceError on any
    unrecognised or implausible result instead of returning junk.
    """
    try:
        p = _Reverso()
        p.feed(html.decode("utf-8", errors="replace"))
        p.close()
    except Exception:
        raise SourceError("Reverso: не удалось разобрать страницу")
    term = " ".join(p.term.split())
    hint = " ".join(p.hint.split())
    if p.broken or not _plausible(term):
        raise SourceError("Reverso: вёрстка не распознана")
    if _BAD.search(hint) or len(hint) > 40:
        hint = ""
    return hint, term


def _compose(hint: str, definition: str, translation: str) -> str:
    out = "(%s) " % hint if hint else ""
    if definition:
        out += definition + " - "
    return out + translation


def _fallback_hint(definition: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", definition)[:2]
    if len(words) < 2 or any(w.lower() in _STOP or len(w) < 3 for w in words):
        return ""
    return " ".join(w.lower() for w in words)


def _reverso(word: str, definition: str) -> str:
    html = http.get_bytes(URL + quote(word, safe=""))
    hint, term = _parse_reverso(html)
    return _compose(hint, definition, term)


def _fallback(word: str, deepl_key: str, definition: str) -> str:
    tr = translate.translate(word, deepl_key).text.strip()
    if not _plausible(tr):
        raise SourceError("перевод слова непригоден")
    return _compose(_fallback_hint(definition), definition, tr)


def get_meaning(word: str, deepl_key: str, dict_entry: Optional[DictEntry]) -> Meaning:
    word = (word or "").strip()
    if not word:
        raise SourceError("пустое слово")
    definition = " ".join((dict_entry.definition if dict_entry else "").split())
    try:
        return Meaning(_reverso(word, definition), "reverso")
    except SourceError:
        pass
    try:
        return Meaning(_fallback(word, deepl_key, definition), "fallback")
    except SourceError as e:
        raise SourceError("значение слова недоступно: %s" % e)
