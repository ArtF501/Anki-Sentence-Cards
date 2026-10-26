"""Clean raw book text. Order of operations matters (see comments)."""
import re

_QUOTES = {
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'",
}
_DASHES = {"–": "-", "—": "-", "−": "-", "\u2010": "-"}
_HEADER_LINE = re.compile(r"^\s*(?:page\s+)?\d+\s*$", re.IGNORECASE)


def normalize_query(query: str) -> str:
    """Same quote and dash folding the book text gets, for user-typed words."""
    for src, dst in {**_QUOTES, **_DASHES}.items():
        query = query.replace(src, dst)
    return query


def normalize(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # 1. join words broken by a hyphen at end of line
    text = re.sub(r"(?<=[a-z])[-\u2010\u00ad]\n[ \t]*(?=[a-z])", "", text)
    text = text.replace("\u00ad", "")
    # a hyphen kept at line end must not gain a space after it
    text = re.sub(r"(?<=[A-Za-z][-\u2010])\n[ \t]*(?=\S)", "", text)
    # 2. drop running headers / page numbers and footnote markers
    text = "\n".join(ln for ln in text.split("\n") if not _HEADER_LINE.match(ln))
    text = re.sub(r"\[\d+\]", "", text)
    # 3. single newlines -> spaces, blank lines stay as paragraph boundaries
    text = text.replace("\xa0", " ")
    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in paragraphs]
    text = "\n\n".join(p for p in paragraphs if p)
    # 4. quotes, dashes, spacing
    return normalize_query(text)
