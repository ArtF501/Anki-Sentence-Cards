"""Word and phrase search over a list of sentences, with simple inflection."""
import re
from dataclasses import dataclass
from typing import List, Tuple

_IRREGULAR = {
    "be": ["is", "are", "was", "were", "been", "being"],
    "begin": ["began", "begun"],
    "bring": ["brought"],
    "buy": ["bought"],
    "come": ["came"],
    "do": ["did", "done"],
    "drink": ["drank", "drunk"],
    "eat": ["ate", "eaten"],
    "fall": ["fell", "fallen"],
    "find": ["found"],
    "get": ["got", "gotten"],
    "give": ["gave", "given"],
    "go": ["went", "gone"],
    "have": ["has", "had"],
    "know": ["knew", "known"],
    "leave": ["left"],
    "make": ["made"],
    "run": ["ran"],
    "say": ["said"],
    "see": ["saw", "seen"],
    "take": ["took", "taken"],
    "think": ["thought"],
    "write": ["wrote", "written"],
}
_IRREGULAR_BACK = {f: b for b, fs in _IRREGULAR.items() for f in fs}
_VOWELS = "aeiou"


def _single_forms(w: str) -> List[str]:
    forms = [w]
    forms += _IRREGULAR.get(w, [])
    if w in _IRREGULAR_BACK:
        base = _IRREGULAR_BACK[w]
        forms.append(base)
        forms += _IRREGULAR[base]
    if w.endswith("ing") and len(w) > 5:
        stem = w[:-3]
        forms += [stem, stem + "e"]
        if stem[-1] == stem[-2]:
            forms.append(stem[:-1])
    if w.endswith("ied") and len(w) > 4:
        forms.append(w[:-3] + "y")
    elif w.endswith("ed") and len(w) > 4:
        stem = w[:-2]
        forms += [stem, stem + "e"]
        if stem[-1] == stem[-2]:
            forms.append(stem[:-1])
    if w.endswith("ies") and len(w) > 4:
        forms.append(w[:-3] + "y")
    elif w.endswith("es") and len(w) > 4:
        forms.append(w[:-2])
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        forms.append(w[:-1])

    if len(w) > 1 and w[-1] == "y" and w[-2] not in _VOWELS:
        forms += [w[:-1] + "ies", w[:-1] + "ied", w + "ing"]
    elif w.endswith("e") and len(w) > 2:
        forms += [w + "s", w + "d", w[:-1] + "ing"]
    else:
        forms += [w + "s", w + "ed", w + "ing"]
        if w.endswith(("s", "x", "z", "ch", "sh")):
            forms.append(w + "es")
        if w.endswith("o"):
            forms.append(w + "es")
        if (
            len(w) >= 3
            and w[-1] not in _VOWELS + "wxy"
            and w[-2] in _VOWELS
            and w[-3] not in _VOWELS
        ):
            forms += [w + w[-1] + "ed", w + w[-1] + "ing"]
    return forms


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def word_forms(query: str) -> List[str]:
    """Search variants for a word or phrase; the exact form comes first.

    For a phrase only the first word is inflected.
    """
    words = query.lower().split()
    if not words:
        return []
    rest = " ".join(words[1:])
    out = []
    for f in _dedupe(_single_forms(words[0])):
        out.append(f + " " + rest if rest else f)
    return out


@dataclass
class Occurrence:
    sentence_index: int
    sentence: str
    matched_form: str
    start: int
    end: int
    exact: bool


def _build_regex(query: str):
    forms = sorted(word_forms(query), key=len, reverse=True)
    alts = [r"\s+".join(re.escape(p) for p in f.split()) for f in forms]
    return re.compile(
        r"(?<![\w'’])(?:" + "|".join(alts) + r")(?![\w'’])",
        re.IGNORECASE,
    )


def find_occurrences(
    sentences: List[str], query: str, limit: int
) -> Tuple[List[Occurrence], bool]:
    """First match per sentence; returns (occurrences, truncated)."""
    if not query.split():
        return [], False
    rx = _build_regex(query)
    exact_norm = " ".join(query.lower().split())
    result: List[Occurrence] = []
    for i, s in enumerate(sentences):
        m = rx.search(s)
        if not m:
            continue
        if len(result) >= limit:
            return result, True
        found = m.group(0)
        result.append(
            Occurrence(i, s, found, m.start(), m.end(),
                       " ".join(found.lower().split()) == exact_norm)
        )
    return result, False


def mark_match(occ: Occurrence) -> str:
    s = occ.sentence
    return s[: occ.start] + "<b>" + s[occ.start : occ.end] + "</b>" + s[occ.end :]
