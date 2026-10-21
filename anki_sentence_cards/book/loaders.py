"""Load a book file (.txt, .epub, .pdf) into raw text."""
import posixpath
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET


class UnsupportedFormat(Exception):
    pass


class BookLoadError(Exception):
    """The book file is unreadable or corrupt."""


def load_text(path: Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    loader = {".txt": _load_txt, ".epub": _load_epub, ".pdf": _load_pdf}.get(ext)
    if loader is None:
        raise UnsupportedFormat("Unsupported book format: %r" % ext)
    try:
        return loader(path)
    except Exception as exc:
        raise BookLoadError("Cannot read %s: %s" % (path.name, exc)) from exc


def _load_txt(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "blockquote", "section",
               "h1", "h2", "h3", "h4", "h5", "h6"}
_SKIP_TAGS = {"script", "style", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _load_epub(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        opf_path = next(e.get("full-path") for e in container.iter()
                        if _local(e.tag) == "rootfile")
        opf = ET.fromstring(z.read(opf_path))
        manifest = {e.get("id"): e.get("href") for e in opf.iter()
                    if _local(e.tag) == "item"}
        spine = [e.get("idref") for e in opf.iter() if _local(e.tag) == "itemref"]
        base = posixpath.dirname(opf_path)
        chapters = []
        for idref in spine:
            href = manifest.get(idref)
            if not href:
                continue
            member = posixpath.normpath(posixpath.join(base, unquote(href.split("#")[0])))
            parser = _TextExtractor()
            parser.feed(z.read(member).decode("utf-8", errors="replace"))
            chapters.append("".join(parser.parts))
    return "\n\n".join(chapters)


def _ensure_typing_extensions() -> None:
    """pypdf does an absolute `from typing_extensions import ...` on Python < 3.11.
    Expose the vendored copy under that name when the environment has none."""
    try:
        import typing_extensions  # noqa: F401
    except ImportError:
        from ..vendor import typing_extensions as vendored

        sys.modules["typing_extensions"] = vendored


def _load_pdf(path: Path) -> str:
    _ensure_typing_extensions()
    from ..vendor import pypdf

    reader = pypdf.PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
