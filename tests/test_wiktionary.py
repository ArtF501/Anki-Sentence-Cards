import json
from pathlib import Path

import pytest

from anki_sentence_cards.sources import http, wiktionary
from anki_sentence_cards.sources.http import SourceError

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / ("wiktionary_%s.json" % name)).read_text(encoding="utf-8"))


@pytest.fixture
def net(monkeypatch):
    state = {"payload": load("supervise"), "gets": []}

    def get_json(url, params=None, timeout=10.0, headers=None):
        state["gets"].append(url)
        if isinstance(state["payload"], Exception):
            raise state["payload"]
        return state["payload"]

    monkeypatch.setattr(http, "get_json", get_json)
    return state


def test_lookup_returns_roles_in_lower_case(net):
    data = wiktionary.lookup("supervise")
    assert [r.pos for r in data.roles] == ["verb", "noun"]
    assert data.roles[0].source == "wiktionary"


def test_lookup_strips_html_from_definitions(net):
    assert wiktionary.lookup("supervise").roles[0].definition == "To oversee and direct."


def test_lookup_gives_no_transcription(net):
    data = wiktionary.lookup("supervise")
    assert data.shared_ipa == "" and all(r.ipa == "" for r in data.roles)


def test_lookup_uses_only_the_english_section(net):
    net["payload"] = {"fr": [{"partOfSpeech": "Verbe", "definitions": [{"definition": "x"}]}]}
    with pytest.raises(SourceError):
        wiktionary.lookup("supervise")


def test_phrase_is_not_sent_to_the_dictionary(net):
    with pytest.raises(SourceError):
        wiktionary.lookup("get along")
    assert net["gets"] == []


def test_strip_markup_unescapes_entities_and_squeezes_space():
    assert wiktionary.strip_markup("<i>a</i>&nbsp;&amp;\n  b ") == "a & b"


@pytest.mark.parametrize("bad", [
    {}, {"en": []}, {"en": "x"}, "x", [], None,
    {"en": [{"partOfSpeech": "", "definitions": [{"definition": "d"}]}]},
])
def test_unusable_payload_raises(bad):
    with pytest.raises(SourceError):
        wiktionary.parse_definitions(bad)


def test_parse_ipa_takes_the_british_pronunciation():
    assert wiktionary.parse_ipa("{{IPA|en|/ˈsuː.pə.vaɪz/|a=RP}}") == "ˈsuː.pə.vaɪz"


def test_parse_ipa_prefers_rp_over_us():
    text = "{{IPA|en|/ˈsuːpɚvaɪz/|a=US}}\n{{IPA|en|/ˈsuːpəvaɪz/|a=RP}}"
    assert wiktionary.parse_ipa(text) == "ˈsuːpəvaɪz"


def test_parse_ipa_returns_empty_on_unknown_shape():
    assert wiktionary.parse_ipa("no templates here") == ""
    assert wiktionary.parse_ipa("{{IPA|ru|/ˈsuːpəvaɪz/}}") == ""   # не английский раздел
    assert wiktionary.parse_ipa("{{IPA|en|}}") == ""


def test_parse_ipa_takes_the_first_when_nothing_is_marked_british():
    assert wiktionary.parse_ipa("{{IPA|en|[ɹʌn]|/xx/}}") == "ɹʌn"


def test_lookup_ipa_reads_the_wikitext_of_the_page(net):
    net["payload"] = {"parse": {"wikitext": "{{IPA|en|/ɹʌn/|a=RP}}"}}
    assert wiktionary.lookup_ipa("run") == "ɹʌn"
    assert net["gets"] == [wiktionary.WIKITEXT_URL]


def test_lookup_ipa_returns_empty_instead_of_raising_on_junk(net):
    net["payload"] = {"parse": {"wikitext": {"*": "nothing"}}}
    assert wiktionary.lookup_ipa("supervise") == ""


def test_lookup_ipa_propagates_a_network_failure(net):
    net["payload"] = SourceError("сервис ответил ошибкой 503")
    with pytest.raises(SourceError):
        wiktionary.lookup_ipa("supervise")
