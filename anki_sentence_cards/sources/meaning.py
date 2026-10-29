"""Candidate meanings of a word: "(hint) English definition - Russian translation".

Primary: the Reverso Context page (HTML, no official API, layout may change).
Fallback: the translator, one option only.

The sources hand back translations, not finished strings: the English part of
the final string comes from the role the user picks, so the string is composed
later, by `compose`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Tuple
from urllib.parse import quote

from . import http, translate
from .http import SourceError

URL = "https://context.reverso.net/translation/english-russian/"
MAX_OPTIONS = 8
_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
_BAD = re.compile(r"[<>{}\d]")
_STOP = {"a", "an", "the", "to", "or", "and", "of", "in", "on", "for", "with",
         "that", "which", "who", "is", "being", "by", "as", "at", "from"}


@dataclass
class MeaningOption:
    hint: str
    translation: str
    source: str              # "reverso" | "fallback"


def _plausible(text: str) -> bool:
    """Shared sanity check for a Russian translation, whichever source gave it."""
    return bool(_CYRILLIC.search(text)) and not _BAD.search(text) and len(text) <= 60


class _Reverso(HTMLParser):
    """Collects (hint, term) of every translation anchor, in page order."""

    def __init__(self):
        super().__init__()
        self.depth_content = 0
        self.in_anchor = False
        self.stopped = False   # broken markup: nothing more is collected
        self.field = None      # "term" / "hint" while inside that span
        self.span_depth = 0    # nesting inside the current field span
        self.term_done = False
        self.hint_done = False
        self.term = ""
        self.hint = ""
        self.pairs = []

    def _abort(self):
        """An anchor boundary reached with a field span still open: broken markup.

        What was already collected stands — including a term that had been read
        in full — and the rest of the page is not read.
        """
        if self.term and not self.field:
            self._flush()
        self.stopped = True
        self.in_anchor = False
        self.field = None

    def _flush(self):
        self.pairs.append((" ".join(self.hint.split()), " ".join(self.term.split())))
        self.term = self.hint = ""
        self.term_done = self.hint_done = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "div" and (a.get("id") == "translations-content" or self.depth_content):
            self.depth_content += 1
        if not self.depth_content or self.stopped:
            return
        if self.field:
            if tag == "a" and "translation" in classes:
                self._abort()
            elif tag == "span":
                self.span_depth += 1
        elif tag == "a" and "translation" in classes:
            if self.in_anchor:  # previous anchor never closed
                self._abort()
                return
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
                return
            self.in_anchor = False
            self._flush()
        elif tag == "div" and self.depth_content:
            self.depth_content -= 1

    def handle_data(self, data):
        if self.in_anchor and not self.stopped:
            if self.field == "term":
                self.term += data
            elif self.field == "hint":
                self.hint += data


def parse_reverso_all(html: bytes) -> List[Tuple[str, str]]:
    """Reverso page -> [(hint, translation), ...] in page order.

    The only place that knows Reverso's layout. Every translation is checked on
    its own: one junk anchor costs its own entry, not the whole list. Raises
    SourceError when not a single plausible pair is left.
    """
    try:
        p = _Reverso()
        p.feed(html.decode("utf-8", errors="replace"))
        p.close()
    except Exception:
        raise SourceError("Reverso: не удалось разобрать страницу")
    out = []
    for hint, term in p.pairs:
        if not _plausible(term):
            continue
        if _BAD.search(hint) or len(hint) > 40:
            hint = ""
        out.append((hint, term))
    if not out:
        raise SourceError("Reverso: вёрстка не распознана")
    return out


def compose(hint: str, definition: str, translation: str) -> str:
    out = "(%s) " % hint if hint else ""
    if definition:
        out += definition + " - "
    return out + translation


def fallback_hint(definition: str) -> str:
    """Two leading words of the definition, when they say anything at all."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", definition or "")[:2]
    if len(words) < 2 or any(w.lower() in _STOP or len(w) < 3 for w in words):
        return ""
    return " ".join(w.lower() for w in words)


def get_meaning_options(word: str, deepl_key: str) -> List[MeaningOption]:
    """Every meaning worth showing the user, best source first.

    Reverso gives the list; when it is unreachable the translator gives one
    option and no hint. Nothing is invented: when neither answers, the caller
    gets a SourceError and the field stays empty.
    """
    word = (word or "").strip()
    if not word:
        raise SourceError("пустое слово")
    try:
        pairs = parse_reverso_all(http.get_bytes(URL + quote(word, safe="")))
        return [MeaningOption(h, t, "reverso") for h, t in pairs[:MAX_OPTIONS]]
    except SourceError:
        pass
    try:
        tr = translate.translate(word, deepl_key).text.strip()
        if not _plausible(tr):
            raise SourceError("перевод слова непригоден")
        return [MeaningOption("", tr, "fallback")]
    except SourceError as e:
        raise SourceError("значение слова недоступно: %s" % e)
