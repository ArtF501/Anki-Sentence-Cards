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


def _cache_path(p, cache):
    return next(cache.glob("*.json"))


def test_corrupt_cache_is_reparsed(tmp_path):
    p, cache = _book(tmp_path), tmp_path / "cache"
    library.load_book(p, cache)
    _cache_path(p, cache).write_text("{not json", encoding="utf-8")
    assert library.load_book(p, cache).sentences == ["One.", "Two."]


def test_wrong_shape_cache_is_reparsed(tmp_path):
    import json

    p, cache = _book(tmp_path), tmp_path / "cache"
    library.load_book(p, cache)
    cf = _cache_path(p, cache)
    mt = json.loads(cf.read_text())["mtime"]
    cf.write_text(json.dumps({"v": 1, "mtime": mt, "sentences": [1, 2]}))
    assert library.load_book(p, cache).sentences == ["One.", "Two."]


def test_old_cache_version_is_reparsed(tmp_path):
    import json

    p, cache = _book(tmp_path), tmp_path / "cache"
    library.load_book(p, cache)
    cf = _cache_path(p, cache)
    d = json.loads(cf.read_text())
    d["v"] = 0
    d["sentences"] = ["stale"]
    cf.write_text(json.dumps(d))
    assert library.load_book(p, cache).sentences == ["One.", "Two."]


def test_unwritable_cache_dir_does_not_break_loading(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert library.load_book(_book(tmp_path), blocker / "sub").sentences == ["One.", "Two."]
