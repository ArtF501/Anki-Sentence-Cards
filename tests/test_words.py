import pytest

from anki_sentence_cards.sources.http import SourceError
from anki_sentence_cards.sources.roles import Role, WordData
from anki_sentence_cards.sources.words import collect_roles


def test_second_source_fills_only_the_missing_transcription():
    primary = lambda w: WordData([Role("verb", "", "to oversee", source="a")])
    backup = lambda w: WordData([Role("verb", "ˈsuːpəvaɪz", "иное", source="b")])
    data = collect_roles("supervise", [primary, backup])
    assert len(data.roles) == 1
    assert data.roles[0].definition == "to oversee"       # победитель по полю, не по записи
    assert data.roles[0].ipa == "ˈsuːpəvaɪz"


def test_backup_is_not_asked_when_the_primary_answered_fully():
    calls = []
    primary = lambda w: WordData([Role("verb", "rʌn", "to move", source="a")])

    def backup(w):
        calls.append(w)
        return WordData([Role("noun", source="b")])

    collect_roles("run", [primary, backup])
    assert calls == []


def test_backup_does_not_add_roles_of_its_own():
    primary = lambda w: WordData([Role("verb", "", "to oversee", source="a")])
    backup = lambda w: WordData([Role("noun", "ˈsuːpəvaɪz", "a thing", source="b")])
    data = collect_roles("supervise", [primary, backup])
    assert [r.pos for r in data.roles] == ["verb"]


def test_lemma_roles_are_labelled_and_last():
    def primary(w):
        if w == "supervised":
            raise SourceError("словарь ничего не знает")
        return WordData([Role("verb", "ˈsuːpəvaɪz", "to oversee", source="a")])

    data = collect_roles("supervised", [primary], candidates=["supervise"])
    assert [(r.pos, r.lemma) for r in data.roles] == [("verb", "supervise")]


def test_lemma_is_asked_even_when_the_word_itself_answered():
    def primary(w):
        return WordData([Role("adjective" if w == "tired" else "noun", source="a")])

    data = collect_roles("tired", [primary], candidates=["tire"])
    assert [(r.pos, r.lemma) for r in data.roles] == [("adjective", ""), ("noun", "tire")]


def test_only_one_lemma_is_accepted():
    primary = lambda w: WordData([Role("noun", source="a")])
    data = collect_roles("supervised", [primary], candidates=["supervise", "supervis"])
    assert {r.lemma for r in data.roles} == {"", "supervise"}


def test_extra_ipa_lookup_runs_only_as_a_last_resort():
    calls = []
    primary = lambda w: WordData([Role("verb", "rʌn", source="a")])
    collect_roles("run", [primary], ipa_lookup=lambda w: calls.append(w) or "x")
    assert calls == []


def test_extra_ipa_lookup_fills_shared_ipa_when_nobody_has_one():
    primary = lambda w: WordData([Role("verb", source="a")])
    data = collect_roles("supervise", [primary], ipa_lookup=lambda w: "ˈsuː.pə.vaɪz")
    assert data.shared_ipa == "ˈsuː.pə.vaɪz"


def test_a_failing_extra_ipa_lookup_does_not_lose_the_roles():
    primary = lambda w: WordData([Role("verb", source="a")])

    def boom(w):
        raise SourceError("сервис ответил ошибкой 503")

    data = collect_roles("supervise", [primary], ipa_lookup=boom)
    assert [r.pos for r in data.roles] == ["verb"] and data.shared_ipa == ""


def test_base_form_transcription_never_becomes_the_shared_one():
    """Транскрипция tire не годится слову tired: она остаётся при помеченной роли."""
    def primary(w):
        if w == "tired":
            return WordData([Role("adjective", source="a")])
        return WordData([Role("noun", source="a")], shared_ipa="taɪə")

    data = collect_roles("tired", [primary], candidates=["tire"],
                         ipa_lookup=lambda w: "" if w == "tired" else "taɪə")
    assert data.shared_ipa == ""
    assert [(r.lemma, r.ipa) for r in data.roles] == [("", ""), ("tire", "taɪə")]


# Review Focus 1
def test_nothing_answers_at_all_raises_with_the_first_reason():
    def dead(w):
        raise SourceError("сервис ответил ошибкой 530")

    with pytest.raises(SourceError) as e:
        collect_roles("prestige", [dead, dead], candidates=["prestig"])
    assert "530" in str(e.value)


@pytest.fixture
def live(monkeypatch):
    from anki_sentence_cards.sources import dictionary, wiktionary, words
    seen = {"dict": [], "wiki": [], "ipa": []}

    def answer(key, pos):
        def inner(w):
            seen[key].append(w)
            if len(w.split()) != 1:      # как настоящие словари: фразу не берут
                raise SourceError("словарь работает только с одним словом")
            return WordData([Role(pos, source=key)])
        return inner

    monkeypatch.setattr(dictionary, "lookup", answer("dict", "verb"))
    monkeypatch.setattr(wiktionary, "lookup", answer("wiki", "noun"))
    monkeypatch.setattr(wiktionary, "lookup_ipa",
                        lambda w: seen["ipa"].append(w) or "ɹʌn")
    return seen


def test_fetch_word_data_asks_the_base_form_of_a_single_word(live):
    from anki_sentence_cards.settings import Settings
    from anki_sentence_cards.sources.words import fetch_word_data
    data = fetch_word_data("cats", Settings())
    assert live["dict"] == ["cats", "cat"]
    assert [(r.pos, r.lemma) for r in data.roles] == [("verb", ""), ("verb", "cat")]


def test_fetch_word_data_never_looks_up_the_parts_of_a_phrase(live):
    from anki_sentence_cards.settings import Settings
    from anki_sentence_cards.sources.words import fetch_word_data
    with pytest.raises(SourceError):
        fetch_word_data("get along", Settings())
    assert live["dict"] == ["get along"] and live["ipa"] == []


def test_fetch_word_data_honours_the_wiktionary_ipa_switch(live):
    from anki_sentence_cards.settings import Settings
    from anki_sentence_cards.sources.words import fetch_word_data
    assert fetch_word_data("cats", Settings(wiktionary_ipa=False)).shared_ipa == ""
    assert live["ipa"] == []
    assert fetch_word_data("cats", Settings(wiktionary_ipa=True)).shared_ipa == "ɹʌn"


def test_lemma_transcription_fills_the_same_part_of_speech_of_the_word():
    """supervised: своя роль без транскрипции берёт её у supervise — та же часть речи."""
    def primary(w):
        if w == "supervised":
            return WordData([Role("verb", "", "past of supervise", source="a")])
        return WordData([Role("verb", "ˈsuːpəvaɪz", "To oversee and direct.", source="a")])

    data = collect_roles("supervised", [primary], candidates=["supervise"])
    assert [(r.pos, r.ipa, r.lemma) for r in data.roles] == [
        ("verb", "ˈsuːpəvaɪz", ""), ("verb", "ˈsuːpəvaɪz", "supervise")]


def test_lemma_transcription_never_crosses_to_another_part_of_speech():
    """tired — adjective, tire — noun: /taɪə/ не имеет права переехать на tired."""
    def primary(w):
        if w == "tired":
            return WordData([Role("adjective", "", "worn out", source="a")])
        return WordData([Role("noun", "taɪə", "rubber ring", source="a")])

    data = collect_roles("tired", [primary], candidates=["tire"])
    assert [(r.pos, r.ipa) for r in data.roles] == [("adjective", ""), ("noun", "taɪə")]
