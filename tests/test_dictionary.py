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



def test_first_role_is_the_first_part_of_speech(net):
    data = dictionary.lookup("run")
    assert data.roles[0].pos == "verb"
    assert data.roles[0].definition == "To move quickly on foot."
    assert net["gets"] == ["https://api.dictionaryapi.dev/api/v2/entries/en/run"]


def test_part_of_speech_lowercased(net):
    net["payload"] = load("contemporary")
    assert [r.pos for r in dictionary.lookup("contemporary").roles] == ["adjective", "noun"]


def test_ipa_has_no_surrounding_slashes(net):
    net["payload"] = load("contemporary")
    assert dictionary.lookup("contemporary").shared_ipa == "kənˈtɛm.pəˌɹɛɹ.i"


def test_empty_phonetics_skipped_for_next_candidate(net):
    assert dictionary.lookup("run").shared_ipa == "ɹʌn"


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
        dictionary.parse_entries(bad)


def test_phonetic_field_used_when_phonetics_empty():
    p = [{"phonetic": "/ab/", "phonetics": [], "meanings": [{"partOfSpeech": "Noun", "definitions": [{"definition": "d"}]}]}]
    assert dictionary.parse_entries(p).roles == [dictionary.Role("noun", "ab", "d", "", "dictionaryapi")]


@pytest.mark.parametrize("phonetics", [
    {},
    {"phonetics": []},
    {"phonetics": [{"text": "//"}, {"audio": "x"}, {"text": " "}]},
])
def test_no_transcription_keeps_part_of_speech(phonetics):
    entry = dict(phonetics, meanings=[{"partOfSpeech": "Noun", "definitions": [{"definition": "d"}]}])
    data = dictionary.parse_entries([entry])
    assert [(r.pos, r.ipa) for r in data.roles] == [("noun", "")]
    assert data.shared_ipa == ""


@pytest.mark.parametrize("meaning_extra", [
    {},
    {"definitions": []},
    {"definitions": [{}]},
    {"definitions": [{"definition": "  "}]},
])
def test_empty_definition_keeps_part_of_speech_and_ipa(meaning_extra):
    meaning = dict(meaning_extra, partOfSpeech="Noun")
    entry = {"phonetics": [{"text": "/ab/"}], "meanings": [meaning]}
    assert dictionary.parse_entries([entry]).roles == [
        dictionary.Role("noun", "ab", "", "", "dictionaryapi")]


def test_empty_candidates_before_valid_one_are_skipped():
    entry = {
        "phonetic": "//",
        "phonetics": [{"text": "  "}, {"text": "//"}, {"text": "/ɹʌn/"}],
        "meanings": [{"partOfSpeech": "verb", "definitions": [{"definition": "d"}]}],
    }
    assert dictionary.parse_entries([entry]).roles[0].ipa == "ɹʌn"


def test_record_two_entries_tie_ipa_to_each_role(net):
    net["payload"] = load("record")
    data = dictionary.lookup("record")
    assert [(r.pos, r.ipa) for r in data.roles] == [("noun", "ˈrekɔːd"), ("verb", "rɪˈkɔːd")]
    assert data.shared_ipa == ""


def test_multi_role_entry_leaves_its_ipa_shared(net):
    net["payload"] = load("run")
    data = dictionary.lookup("run")
    assert [r.pos for r in data.roles] == ["verb", "noun", "adjective"]   # verb не дважды
    # у записи с двумя ролями транскрипция ничья, у записи с одной — её собственная
    assert [r.ipa for r in data.roles] == ["", "", "xxx"]
    assert data.shared_ipa == "ɹʌn"


def test_every_role_is_labelled_with_its_source(net):
    assert all(r.source == "dictionaryapi" for r in dictionary.lookup("run").roles)


def test_payload_without_any_part_of_speech_raises(net):
    net["payload"] = [{"phonetics": [{"text": "/x/"}]}]
    with pytest.raises(http.SourceError):
        dictionary.lookup("x")
