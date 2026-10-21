from pathlib import Path

import pytest

from anki_sentence_cards.book import loaders
from anki_sentence_cards.book.loaders import UnsupportedFormat, load_text
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
