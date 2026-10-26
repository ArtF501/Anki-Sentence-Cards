"""Split normalized text into sentences."""
import re

_ABBREVIATIONS = {"Mr", "Mrs", "Ms", "Dr", "St", "Prof", "Sr", "Jr", "Mt",
                  "Gen", "Col", "Capt", "Lt", "Sgt", "vs"}
# terminator run, optional closing quotes/brackets, then whitespace
_BOUNDARY = re.compile(r"""([.?!]+['")\]]*)\s+""")
_NEXT_OK = re.compile(r"""['"(\[]*[A-Z0-9]""")
_LAST_WORD = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]+)\.$")


def _is_abbreviation(chunk: str) -> bool:
    m = _LAST_WORD.search(chunk)
    if not m:
        return False
    word = m.group(1)
    # single capital letter is an initial; titles are case-sensitive.
    # "etc." needs no entry: it only splits before a capital (already required).
    return (len(word) == 1 and word.isupper()) or word in _ABBREVIATIONS


def _split_paragraph(par: str) -> list:
    out = []
    start = 0
    for m in _BOUNDARY.finditer(par):
        end = m.end(1)
        term = m.group(1)
        if term.rstrip("'\")]") == "." and _is_abbreviation(par[start:end].rstrip("'\")]")):
            continue
        if not _NEXT_OK.match(par, m.end()):
            continue
        out.append(par[start:end])
        start = m.end()
    out.append(par[start:])
    return [s.strip() for s in out if s.strip()]


def split_sentences(text: str) -> list:
    sentences = []
    for par in re.split(r"\n\s*\n", text):
        par = par.strip()
        if par:
            sentences.extend(_split_paragraph(par))
    return sentences
