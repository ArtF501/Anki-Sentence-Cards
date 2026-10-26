from pathlib import Path

import pytest

from anki_sentence_cards.sources import http, meaning, translate
from anki_sentence_cards.sources.http import SourceError
from anki_sentence_cards.sources.meaning import (
    MAX_OPTIONS, MeaningOption, compose, fallback_hint, get_meaning_options,
    parse_reverso_all,
)

FIX = Path(__file__).parent / "fixtures"
DEFN = "person or thing considered modern or current"


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


def _page(inner):
    return ('<div id="translations-content">%s</div>' % inner).encode("utf-8")


def _anchor(term, hint=""):
    span = '<span class="context-hint">%s</span>' % hint if hint else ""
    return '<a class="translation"><span class="display-term">%s</span>%s</a>' % (term, span)


# ---- parse_reverso_all

def test_parse_reverso_all_returns_every_translation_in_order():
    page = (FIX / "reverso_run.html").read_bytes()
    assert parse_reverso_all(page) == [("", "бежать"), ("about", "бегать"), ("", "запускать")]


def test_parse_reverso_all_reads_the_hint_of_each_anchor():
    page = (FIX / "reverso_contemporary.html").read_bytes()
    assert parse_reverso_all(page) == [("modern time", "современник"), ("", "современный")]


def test_parse_reverso_all_drops_implausible_entries_and_keeps_the_rest():
    page = _page(_anchor("latin") + _anchor("бежать") + _anchor("слово2"))
    assert parse_reverso_all(page) == [("", "бежать")]


@pytest.mark.parametrize("page", [
    b"<html></html>",
    b"<html><body>Just a moment...</body></html>",
    b"",
    _page(_anchor("x")),
    _page(_anchor("")),
    b'<div id="other"><a class="translation"><span class="display-term">\xd1\x81\xd0\xbb\xd0\xbe\xd0\xb2\xd0\xbe</span></a></div>',
])
def test_parse_reverso_all_raises_when_nothing_is_plausible(page):
    with pytest.raises(SourceError):
        parse_reverso_all(page)


def test_parser_nested_span_does_not_truncate_term():
    html = _page('<a class="translation"><span class="display-term">совре<span>менн</span>ик</span></a>')
    assert parse_reverso_all(html) == [("", "современник")]


def test_parser_unclosed_anchor_stops_the_parse_and_keeps_what_it_had():
    html = _page('<a class="translation"><span class="display-term">современник</span>'
                 '<a class="translation"><span class="display-term">современный</span></a>')
    assert parse_reverso_all(html) == [("", "современник")]


@pytest.mark.parametrize("term", ["слово2", "я" * 61])
def test_parser_rejects_digits_and_overlong_term(term):
    with pytest.raises(SourceError):
        parse_reverso_all(_page(_anchor(term)))


def test_parser_drops_an_implausible_hint_but_keeps_the_translation():
    assert parse_reverso_all(_page(_anchor("бежать", "hint7"))) == [("", "бежать")]
    assert parse_reverso_all(_page(_anchor("бежать", "x" * 41))) == [("", "бежать")]


def test_unclosed_inner_span_does_not_glue_terms():
    html = _page('<a class="translation"><span class="display-term">слово<span>x</a>'
                 '<a class="translation"><span class="display-term">другое</span></a>')
    try:
        pairs = parse_reverso_all(html)
    except SourceError:
        return
    assert pairs[0][1] == "слово"


# ---- compose / fallback_hint

def test_compose_matches_the_card_format():
    assert compose("about", "to move fast", "бегать") == "(about) to move fast - бегать"
    assert compose("", "", "бежать") == "бежать"
    assert compose("", DEFN, "современник") == DEFN + " - современник"
    assert compose("about", "", "бегать") == "(about) бегать"


def test_fallback_hint_takes_two_meaningful_words():
    assert fallback_hint("modern period of time") == "modern period"


@pytest.mark.parametrize("definition", ["", "Run", DEFN, "a thing"])
def test_fallback_hint_stays_empty_without_two_meaningful_words(definition):
    assert fallback_hint(definition) == ""


# ---- get_meaning_options

def test_options_come_from_reverso_when_it_answers(net):
    opts = get_meaning_options("contemporary", "")
    assert [(o.hint, o.translation, o.source) for o in opts] == [
        ("modern time", "современник", "reverso"), ("", "современный", "reverso")]
    assert net["gets"] == ["https://context.reverso.net/translation/english-russian/contemporary"]


def test_options_are_capped(net):
    net["page"] = _page("".join(_anchor("вариант" + "а" * i) for i in range(20)))
    assert len(get_meaning_options("run", "")) == MAX_OPTIONS


@pytest.mark.parametrize("page", [SourceError("down"), b"<html>changed layout</html>", b""])
def test_fallback_gives_exactly_one_option_when_reverso_is_dead(net, page):
    net["page"] = page
    opts = get_meaning_options("run", "")
    assert len(opts) == 1 and opts[0].source == "fallback" and opts[0].hint == ""
    assert opts[0].translation == "современник"


@pytest.mark.parametrize("bad", ["<html>429</html>", "contemporary", "я" * 61, "  "])
def test_fallback_rejects_a_junk_translation(net, bad):
    net["page"] = SourceError("down")
    net["tr"] = bad
    with pytest.raises(SourceError):
        get_meaning_options("contemporary", "")


def test_everything_dead_raises(net):
    net["page"] = SourceError("down")
    net["tr"] = SourceError("down")
    with pytest.raises(SourceError):
        get_meaning_options("run", "")


def test_empty_word_raises(net):
    with pytest.raises(SourceError):
        get_meaning_options("  ", "")
    assert net["gets"] == []
