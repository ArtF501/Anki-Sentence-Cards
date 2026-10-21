import sys
import zipfile
from pathlib import Path

import pytest

from anki_sentence_cards.book import loaders
from anki_sentence_cards.book.loaders import BookLoadError, UnsupportedFormat, load_text
from anki_sentence_cards.vendor import typing_extensions as vendored_te
from anki_sentence_cards.book.normalize import normalize
from anki_sentence_cards.book.sentences import split_sentences

FIX = Path(__file__).parent / "fixtures"
OPENING = "The light of the old lamp fell across the table where Mr. Angier sat waiting."


@pytest.mark.parametrize("name", ["sample.txt", "sample.epub", "sample.pdf"])
def test_all_formats_give_same_opening_sentence(name):
    sentences = split_sentences(normalize(load_text(FIX / name)))
    assert sentences[0] == OPENING


def test_formats_agree_on_sentence_count():
    counts = {
        n: len(split_sentences(normalize(load_text(FIX / n))))
        for n in ("sample.txt", "sample.epub", "sample.pdf")
    }
    assert len(set(counts.values())) == 1, counts


def test_unsupported_extension_raises(tmp_path):
    p = tmp_path / "book.docx"
    p.write_bytes(b"x")
    with pytest.raises(UnsupportedFormat):
        load_text(p)
    assert issubclass(UnsupportedFormat, Exception) and loaders.UnsupportedFormat is UnsupportedFormat


def test_txt_non_utf8_encoding_is_decoded(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes("café “ok”".encode("cp1252"))
    assert load_text(p) == "café “ok”"


def test_pdf_loads_without_system_typing_extensions(monkeypatch):
    # None in sys.modules makes `import typing_extensions` raise ImportError,
    # as on a Python 3.9 Anki without the package.
    monkeypatch.setitem(sys.modules, "typing_extensions", None)
    text = load_text(FIX / "sample.pdf")
    assert text.startswith("The light of the old lamp")
    assert sys.modules["typing_extensions"] is vendored_te


@pytest.mark.parametrize("name,data", [
    ("bad.epub", b"not a zip"),
    ("bad.pdf", b"not a pdf"),
])
def test_corrupt_files_raise_book_load_error(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    with pytest.raises(BookLoadError):
        load_text(p)


def test_epub_without_rootfile_raises_book_load_error(tmp_path):
    p = tmp_path / "x.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("META-INF/container.xml", "<container><rootfiles/></container>")
    with pytest.raises(BookLoadError):
        load_text(p)


def test_epub_broken_manifest_raises_book_load_error(tmp_path):
    p = tmp_path / "x.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="c.opf"/></rootfiles></container>')
        z.writestr("c.opf", '<package><manifest><item id="a" href="missing.xhtml"/></manifest><spine><itemref idref="a"/></spine></package>')
    with pytest.raises(BookLoadError):
        load_text(p)


def test_missing_txt_raises_book_load_error(tmp_path):
    with pytest.raises(BookLoadError):
        load_text(tmp_path / "nope.txt")
