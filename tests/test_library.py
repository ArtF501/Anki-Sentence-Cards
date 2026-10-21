from anki_sentence_cards.book import library


def _book(tmp_path, text="One. Two."):
    p = tmp_path / "b.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_book_returns_sentences(tmp_path):
    b = library.load_book(_book(tmp_path), tmp_path / "cache")
    assert b.sentences == ["One.", "Two."]


def test_second_load_uses_cache_and_does_not_reparse(tmp_path, monkeypatch):
    p, cache = _book(tmp_path), tmp_path / "cache"
    first = library.load_book(p, cache)

    def boom(*a, **k):
        raise AssertionError("reparsed")

    monkeypatch.setattr(library, "load_text", boom)
    assert library.load_book(p, cache).sentences == first.sentences


def test_cache_invalidated_when_file_mtime_changes(tmp_path):
    import os

    p, cache = _book(tmp_path), tmp_path / "cache"
    library.load_book(p, cache)
    p.write_text("Alpha. Beta. Gamma.", encoding="utf-8")
    st = p.stat()
    os.utime(p, (st.st_atime, st.st_mtime + 10))
    assert len(library.load_book(p, cache).sentences) == 3
