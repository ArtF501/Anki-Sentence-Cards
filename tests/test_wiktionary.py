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

    def get_json(url, params=None, headers=None, timeout=10.0):
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
