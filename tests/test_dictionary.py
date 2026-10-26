import json
from pathlib import Path

import pytest

from anki_sentence_cards.sources import dictionary, http

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / ("dictionaryapi_%s.json" % name)).read_text(encoding="utf-8"))


@pytest.fixture
def net(monkeypatch):
    state = {"payload": load("run"), "gets": []}

    def get_json(url, params=None, headers=None, timeout=10.0):
        state["gets"].append(url)
        if isinstance(state["payload"], Exception):
            raise state["payload"]
        return state["payload"]

    monkeypatch.setattr(http, "get_json", get_json)
    return state


def test_first_part_of_speech_taken(net):
    e = dictionary.lookup("run")
    assert e.part_of_speech == "verb"
    assert e.definition == "To move quickly on foot."
    assert net["gets"] == ["https://api.dictionaryapi.dev/api/v2/entries/en/run"]


def test_part_of_speech_lowercased(net):
    net["payload"] = load("contemporary")
    assert dictionary.lookup("contemporary").part_of_speech == "adjective"


def test_ipa_has_no_surrounding_slashes(net):
    net["payload"] = load("contemporary")
    assert dictionary.lookup("contemporary").ipa == "kənˈtɛm.pəˌɹɛɹ.i"


def test_empty_phonetics_skipped_for_next_candidate(net):
    assert dictionary.lookup("run").ipa == "ɹʌn"


def test_unknown_word_raises_source_error(net):
    net["payload"] = {"title": "No Definitions Found"}
    with pytest.raises(http.SourceError):
        dictionary.lookup("qwertyzzz")


@pytest.mark.parametrize("phrase", ["ice cream", " ice  cream ", "a\tb", "", "   "])
def test_multiword_phrase_is_not_requested(net, phrase):
    with pytest.raises(http.SourceError):
        dictionary.lookup(phrase)
    assert net["gets"] == []


@pytest.mark.parametrize("bad", [
    {"title": "No Definitions Found"}, [], "x", [1], [{}],
    [{"phonetics": [{"text": "/a/"}], "meanings": []}],
    [{"phonetics": [{"text": "/a/"}], "meanings": [{"partOfSpeech": "", "definitions": [{"definition": "d"}]}]}],
    [{"phonetics": "oops", "meanings": [{"partOfSpeech": "noun", "definitions": [{"definition": "d"}]}]}],
])
def test_parse_rejects_wrong_shapes(bad):
    with pytest.raises(http.SourceError):
        dictionary.parse_entry(bad)


def test_phonetic_field_used_when_phonetics_empty():
    p = [{"phonetic": "/ab/", "phonetics": [], "meanings": [{"partOfSpeech": "Noun", "definitions": [{"definition": "d"}]}]}]
    assert dictionary.parse_entry(p) == dictionary.DictEntry("noun", "ab", "d")


@pytest.mark.parametrize("phonetics", [
    {},
    {"phonetics": []},
    {"phonetics": [{"text": "//"}, {"audio": "x"}, {"text": " "}]},
])
def test_no_transcription_keeps_part_of_speech(phonetics):
    entry = dict(phonetics, meanings=[{"partOfSpeech": "Noun", "definitions": [{"definition": "d"}]}])
    assert dictionary.parse_entry([entry]) == dictionary.DictEntry("noun", "", "d")


@pytest.mark.parametrize("meaning_extra", [
    {},
    {"definitions": []},
    {"definitions": [{}]},
    {"definitions": [{"definition": "  "}]},
])
def test_empty_definition_keeps_part_of_speech_and_ipa(meaning_extra):
    meaning = dict(meaning_extra, partOfSpeech="Noun")
    entry = {"phonetics": [{"text": "/ab/"}], "meanings": [meaning]}
    assert dictionary.parse_entry([entry]) == dictionary.DictEntry("noun", "ab", "")


def test_empty_candidates_before_valid_one_are_skipped():
    entry = {
        "phonetic": "//",
        "phonetics": [{"text": "  "}, {"text": "//"}, {"text": "/ɹʌn/"}],
        "meanings": [{"partOfSpeech": "verb", "definitions": [{"definition": "d"}]}],
    }
    assert dictionary.parse_entry([entry]).ipa == "ɹʌn"
