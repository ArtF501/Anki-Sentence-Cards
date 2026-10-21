"""Clean raw book text. Order of operations matters (see comments)."""
import re

_QUOTES = {
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'",
}
_DASHES = {"–": "-", "—": "-", "−": "-"}
_HEADER_LINE = re.compile(r"^\s*(?:page\s+)?\d+\s*$", re.IGNORECASE)


def normalize(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # 1. join words broken by a hyphen at end of line
    text = re.sub(r"(?<=[a-z])[-\u2010\u00ad]\n(?=[a-z])", "", text)
    text = text.replace("\u00ad", "")
    # a hyphen kept at line end must not gain a space after it
    text = re.sub(r"(?<=[A-Za-z][-\u2010])\n(?=\S)", "", text)
    # 2. drop running headers / page numbers and footnote markers
    text = "\n".join(ln for ln in text.split("\n") if not _HEADER_LINE.match(ln))
    text = re.sub(r"\[\d+\]", "", text)
    # 3. single newlines -> spaces, blank lines stay as paragraph boundaries
    text = text.replace("\xa0", " ")
    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in paragraphs]
    text = "\n\n".join(p for p in paragraphs if p)
    # 4. quotes, dashes, spacing
    for src, dst in {**_QUOTES, **_DASHES}.items():
        text = text.replace(src, dst)
    return text
