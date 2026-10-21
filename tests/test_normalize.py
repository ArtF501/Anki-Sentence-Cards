from pathlib import Path

from anki_sentence_cards.book.normalize import normalize


def test_hyphen_linebreak_is_joined():
    assert "contemporary" in normalize("contem-\nporary man")


def test_real_hyphen_before_newline_with_capital_is_kept():
    assert "Anglo-" in normalize("the Anglo-\nSaxon king")


def test_paragraph_internal_newlines_become_spaces():
    assert normalize("one\ntwo\nthree\n\nfour") == "one two three\n\nfour"


def test_curly_quotes_and_dashes_normalized():
    out = normalize("“I can’t,” he said — ‘no’.")
    assert out == "\"I can't,\" he said - 'no'."


def test_page_headers_and_footnote_markers_removed():
    out = normalize("Page 42\n\nHello there.[3] Next\nline.\n\n17\n\nEnd.")
    assert "Page 42" not in out and "[3]" not in out and "17" not in out
    assert out == "Hello there. Next line.\n\nEnd."


def test_broken_lines_fixture():
    raw = (Path(__file__).parent / "fixtures" / "broken_lines.txt").read_text(encoding="utf-8")
    out = normalize(raw)
    assert "contemporary" in out
    assert "Page" not in out and "[3]" not in out
    assert "\"I can't wait,\" he said, \"for the next train.\"" in out


def test_unicode_hyphen_and_soft_hyphen_are_joined():
    assert "contemporary" in normalize("contem‐\nporary man")
    assert "contemporary" in normalize("contem­\nporary man")


def test_kept_hyphen_gets_no_space():
    assert normalize("the Anglo-\nSaxon king") == "the Anglo-Saxon king"


def test_normalize_query_folds_quotes_and_dashes():
    from anki_sentence_cards.book.normalize import normalize_query
    assert normalize_query("don’t well–known") == "don't well-known"


def test_hyphen_join_survives_indented_continuation():
    assert normalize("inter-\n   esting") == "interesting"
    assert normalize("Anglo-\n   Saxon") == "Anglo-Saxon"
    assert normalize("end-\n\nNext") == "end-\n\nNext"


def test_u2010_hyphen_is_folded():
    assert normalize("well‐known") == "well-known"
