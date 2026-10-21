from pathlib import Path

import pytest

from anki_sentence_cards.sources import http, meaning, translate
from anki_sentence_cards.sources.dictionary import DictEntry
from anki_sentence_cards.sources.http import SourceError
from anki_sentence_cards.sources.meaning import Meaning, get_meaning

FIX = Path(__file__).parent / "fixtures"
DEFN = "person or thing considered modern or current"
ENTRY = DictEntry("adjective", "x", DEFN)


@pytest.fixture
def net(monkeypatch):
    s = {"page": (FIX / "reverso_contemporary.html").read_bytes(), "tr": "современник", "gets": []}

    def get_bytes(url, params=None, timeout=10.0):
        s["gets"].append(url)
        if isinstance(s["page"], Exception):
            raise s["page"]
        return s["page"]

    def tr(text, key, target="RU"):
        if isinstance(s["tr"], Exception):
            raise s["tr"]
        return translate.Translation(s["tr"], "google")

    monkeypatch.setattr(http, "get_bytes", get_bytes)
    monkeypatch.setattr(translate, "translate", tr)
    return s


def test_reverso_translation_used_when_available(net):
    m = get_meaning("contemporary", "", ENTRY)
    assert m.source == "reverso"
    assert net["gets"] == ["https://context.reverso.net/translation/english-russian/contemporary"]


def test_format_matches_sample_card(net):
    assert get_meaning("contemporary", "", ENTRY).text == (
        "(modern time) person or thing considered modern or current - современник")


def test_parser_takes_first_translation_only():
    html = (FIX / "reverso_contemporary.html").read_bytes()
    assert meaning._parse_reverso(html) == ("modern time", "современник")


@pytest.mark.parametrize("page", [
    b"<html><body>Just a moment...</body></html>",
    b"",
    b'<div id="translations-content"><a class="translation"><span class="display-term">x</span></a></div>',
    b'<div id="translations-content"><a class="translation"><span class="display-term"></span></a></div>',
    b'<div id="other"><a class="translation"><span class="display-term">\xd1\x81\xd0\xbb\xd0\xbe\xd0\xb2\xd0\xbe</span></a></div>',
])
def test_parser_rejects_unrecognised_layout(page):
    with pytest.raises(SourceError):
        meaning._parse_reverso(page)


@pytest.mark.parametrize("page", [
    SourceError("down"), b"<html>changed layout</html>", b""])
def test_falls_back_to_dictionary_plus_translator_when_reverso_fails(net, page):
    net["page"] = page
    m = get_meaning("contemporary", "", ENTRY)
    assert m.source == "fallback"
    assert m.text.endswith(DEFN + " - современник")


def test_fallback_keeps_the_same_three_part_shape(net):
    net["page"] = SourceError("down")
    e = DictEntry("noun", "", "modern period of time")
    assert get_meaning("w", "", e).text == "(modern period) modern period of time - современник"


def test_fallback_omits_parens_without_meaningful_hint(net):
    net["page"] = SourceError("down")
    assert get_meaning("w", "", ENTRY).text == DEFN + " - современник"
    one = DictEntry("noun", "", "Run")
    assert get_meaning("w", "", one).text == "Run - современник"


def test_fallback_survives_empty_definition_and_missing_entry(net):
    net["page"] = SourceError("down")
    assert get_meaning("w", "", DictEntry("noun", "", "")).text == "современник"
    assert get_meaning("w", "", None).text == "современник"


def test_fallback_rejects_junk_translation(net):
    net["page"] = SourceError("down")
    net["tr"] = "<html>429</html>"
    with pytest.raises(SourceError):
        get_meaning("w", "", ENTRY)


def test_all_sources_dead_raises_source_error(net):
    net["page"] = SourceError("down")
    net["tr"] = SourceError("down")
    with pytest.raises(SourceError):
        get_meaning("w", "", ENTRY)


def test_empty_word_raises(net):
    with pytest.raises(SourceError):
        get_meaning("  ", "", ENTRY)


def _page(inner):
    return ('<div id="translations-content">%s</div>' % inner).encode("utf-8")


def test_parser_nested_span_does_not_truncate_term():
    html = _page('<a class="translation"><span class="display-term">совре<span>менн</span>ик</span></a>')
    assert meaning._parse_reverso(html) == ("", "современник")


def test_parser_unclosed_anchor_does_not_glue_terms():
    html = _page('<a class="translation"><span class="display-term">современник</span>'
                 '<a class="translation"><span class="display-term">современный</span></a>')
    assert meaning._parse_reverso(html) == ("", "современник")


@pytest.mark.parametrize("term", ["слово2", "я" * 61])
def test_parser_rejects_digits_and_overlong_term(term):
    html = _page('<a class="translation"><span class="display-term">%s</span></a>' % term)
    with pytest.raises(SourceError):
        meaning._parse_reverso(html)


def test_fallback_rejects_untranslated_latin(net):
    net["page"] = SourceError("down")
    net["tr"] = "contemporary"
    with pytest.raises(SourceError):
        get_meaning("contemporary", "", ENTRY)


def test_fallback_rejects_overlong_translation(net):
    net["page"] = SourceError("down")
    net["tr"] = "я" * 61
    with pytest.raises(SourceError):
        get_meaning("w", "", ENTRY)


def test_reverso_path_with_empty_definition_and_no_entry(net):
    assert get_meaning("w", "", DictEntry("noun", "", "")).text == "(modern time) современник"
    assert get_meaning("w", "", None).text == "(modern time) современник"


def test_unclosed_inner_span_does_not_glue_terms():
    html = _page('<a class="translation"><span class="display-term">слово<span>x</a>'
                 '<a class="translation"><span class="display-term">другое</span></a>')
    try:
        _, term = meaning._parse_reverso(html)
    except SourceError:
        return
    assert term == "слово"
