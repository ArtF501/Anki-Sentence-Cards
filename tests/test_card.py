import pytest

from anki_sentence_cards.book.search import Occurrence
from anki_sentence_cards.card import CardDraft, build_draft, chosen_role, resolve_choices
from anki_sentence_cards.settings import Settings
from anki_sentence_cards.sources import meaning, translate, tts, words
from anki_sentence_cards.sources.http import SourceError
from anki_sentence_cards.sources.meaning import MeaningOption
from anki_sentence_cards.sources.roles import Role, WordData

SENT = "He had to give up smoking."
KEYS = {"front", "translate", "pos", "ipa", "meaning", "sound"}
RECORD = WordData([Role("noun", "ˈrekɔːd", "a thing constituting a piece of evidence"),
                   Role("verb", "rɪˈkɔːd", "set down in writing")])


def occ_for(form):
    i = SENT.index(form)
    return Occurrence(0, SENT, form, i, i + len(form), True)


def occ_any():
    """A hand-typed sentence: the word is not in it, so nothing is bolded."""
    return Occurrence(0, SENT, "", 0, 0, False)


@pytest.fixture
def src(monkeypatch):
    s = {"tr": translate.Translation("Ему пришлось бросить курить.", "google"),
         "dict": WordData([Role("verb", "ɡɪv", "stop doing")]),
         "mean": [MeaningOption("", "бросить", "reverso")],
         "audio": b"MP3DATA",
         "words": {
             "record": RECORD,
             "run": WordData([Role("verb"), Role("noun"), Role("adjective")], "ɹʌn"),
             "supervise": WordData([Role("verb", "", "To oversee and direct.")]),
             "prestige": SourceError("сервис ответил ошибкой 530"),
         },
         "means": {
             "record": [MeaningOption("", "запись", "reverso")],
             "supervise": [MeaningOption("", "наблюдать", "fallback")],
         },
         "lookups": []}

    def pick(key):
        v = s[key]
        if isinstance(v, Exception):
            raise v
        return v

    def fetch(word, settings):
        s["lookups"].append(word)
        v = s["words"][word] if word in s["words"] else pick("dict")
        if isinstance(v, Exception):
            raise v
        return v

    def options(word, key):
        return s["means"][word] if word in s["means"] else pick("mean")

    s["calls"] = {}

    def rec(name, fn):
        def w(*args, **kw):
            s["calls"][name] = (args, kw)
            return fn(*args, **kw)
        return w

    monkeypatch.setattr(translate, "translate", rec("tr", lambda text, key, target="RU": pick("tr")))
    monkeypatch.setattr(words, "fetch_word_data", rec("dict", fetch))
    monkeypatch.setattr(meaning, "get_meaning_options", rec("mean", options))
    monkeypatch.setattr(tts, "synthesize", rec("audio", lambda w, lang="en-GB": pick("audio")))
    return s


# ---- build_draft gathers, chooses nothing

def test_build_draft_keeps_all_variants_and_chooses_nothing(src):
    d = build_draft("record", occ_any(), Settings())
    assert [r.pos for r in d.roles] == ["noun", "verb"]
    assert d.role_index == 0 and d.meaning_index == 0
    assert d.values["pos"] == "" and d.values["meaning"] == ""   # до resolve поля пусты
    assert d.values["ipa"] == ""


def test_front_contains_bolded_form(src):
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.values["front"] == "He had to give up <b>smoking</b>."
    assert set(d.values) == KEYS
    assert d.missing == [] and d.errors == []


def test_sound_field_is_anki_sound_tag(src):
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.values["sound"] == "[sound:%s]" % d.audio_name
    assert d.audio == b"MP3DATA" and d.audio_name.endswith(".mp3")


def test_phrase_gets_one_role_and_no_dictionary_call(src):
    d = build_draft("give up", occ_for("give up"), Settings())
    assert [r.pos for r in d.roles] == ["phrase"]
    assert src["lookups"] == []
    assert d.meanings                            # значение для фразы всё равно добывается


# ---- resolve_choices turns a choice into fields

def test_resolve_writes_the_chosen_role_and_its_transcription(src):
    d = build_draft("record", occ_any(), Settings())
    d.role_index = 1
    resolve_choices(d)
    assert d.values["pos"] == "verb" and d.values["ipa"] == "rɪˈkɔːd"


def test_resolve_falls_back_to_the_shared_transcription(src):
    d = build_draft("run", occ_any(), Settings())
    resolve_choices(d)
    assert d.values["ipa"] == d.shared_ipa == "ɹʌn" and "ipa" not in d.missing


def test_resolve_puts_the_definition_of_the_chosen_role_into_meaning(src):
    d = build_draft("record", occ_any(), Settings())
    d.role_index, d.meaning_index = 1, 0
    resolve_choices(d)
    assert "set down in writing" in d.values["meaning"]
    assert d.values["meaning"].endswith(" - запись")


def test_resolve_builds_the_hint_for_a_fallback_option(src):
    src["words"]["supervise"] = WordData([Role("verb", "", "watchful oversight of work")])
    d = build_draft("supervise", occ_any(), Settings())
    resolve_choices(d)
    assert d.values["meaning"] == "(watchful oversight) watchful oversight of work - наблюдать"


def test_resolve_invents_no_hint_when_the_definition_starts_with_a_stop_word(src):
    d = build_draft("supervise", occ_any(), Settings())   # "To oversee and direct."
    resolve_choices(d)
    assert d.values["meaning"] == "To oversee and direct. - наблюдать"


def test_resolve_keeps_the_hint_reverso_gave(src):
    src["means"]["record"] = [MeaningOption("about", "запись", "reverso")]
    d = build_draft("record", occ_any(), Settings())
    resolve_choices(d)
    assert d.values["meaning"].startswith("(about) ")


def test_resolve_marks_empty_fields_as_missing(src):
    d = build_draft("prestige", occ_any(), Settings())
    resolve_choices(d)
    assert "pos" in d.missing and "ipa" in d.missing
    assert any("530" in e for e in d.errors)
    assert d.values["meaning"]                   # значение добылось и без словаря


def test_resolve_is_idempotent(src):
    d = build_draft("record", occ_any(), Settings())
    resolve_choices(d)
    first = dict(d.values)
    resolve_choices(d)
    assert d.values == first and len(d.missing) == len(set(d.missing))


def test_resolve_after_a_changed_choice_clears_the_old_missing_mark(src):
    src["words"]["record"] = WordData([Role(""), Role("verb", "rɪˈkɔːd", "set down")])
    d = build_draft("record", occ_any(), Settings())
    resolve_choices(d)
    assert "pos" in d.missing
    d.role_index = 1
    resolve_choices(d)
    assert "pos" not in d.missing and d.values["pos"] == "verb"


def test_resolve_survives_an_index_out_of_range(src):
    d = build_draft("record", occ_any(), Settings())
    d.role_index, d.meaning_index = 99, 99
    resolve_choices(d)
    assert d.values["pos"] == "noun" and d.values["meaning"]


def test_resolve_of_a_phrase_does_not_report_a_missing_transcription(src):
    d = build_draft("give up", occ_for("give up"), Settings())
    resolve_choices(d)
    assert d.values["pos"] == "phrase" and d.values["ipa"] == ""
    assert "ipa" not in d.missing and "pos" not in d.missing


def test_chosen_role_is_none_without_roles():
    assert chosen_role(CardDraft("x", {})) is None


def test_resolve_without_any_variants_marks_everything_missing(src):
    src["dict"] = SourceError("нет")
    src["mean"] = SourceError("нет")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert {"pos", "ipa", "meaning"} <= set(d.missing)
    assert d.values["pos"] == "" and d.values["meaning"] == ""


# ---- isolation: one dead source never stops the card

def test_failed_source_leaves_field_empty_and_records_it(src):
    src["tr"] = SourceError("DeepL недоступен")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert "translate" in d.missing and d.values["translate"] == ""


def test_one_dead_source_does_not_stop_the_others(src):
    src["tr"] = SourceError("x")
    src["dict"] = SourceError("y")
    src["audio"] = SourceError("z")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert d.values["front"] and d.values["meaning"]
    assert d.values["sound"] == "" and d.audio is None and d.audio_name == ""
    assert set(d.missing) == {"translate", "pos", "ipa", "sound"}


def test_errors_carry_human_readable_reason(src):
    src["tr"] = SourceError("DeepL недоступен")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert any("DeepL недоступен" in e for e in d.errors)


def test_meaning_failure_is_isolated(src):
    src["mean"] = SourceError("нет")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert d.values["meaning"] == "" and "meaning" in d.missing
    assert d.values["translate"] and d.values["sound"]


def test_dictionary_failure_leaves_the_meaning_without_an_english_part(src):
    src["dict"] = SourceError("нет")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert d.values["meaning"] == "бросить"


def test_empty_ipa_is_missing_but_pos_kept(src):
    src["dict"] = WordData([Role("verb", "", "def")])
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert d.values["pos"] == "verb" and d.values["ipa"] == ""
    assert d.missing == ["ipa"]


def test_blank_results_are_not_passed_as_success(src):
    src["tr"] = translate.Translation("  ", "google")
    src["mean"] = [MeaningOption("", "  ", "reverso")]
    src["audio"] = b""
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert set(d.missing) == {"translate", "meaning", "sound"}
    assert d.values["sound"] == "" and d.audio is None


def test_unexpected_exception_is_isolated(src):
    for key in ("tr", "dict", "mean", "audio"):
        src[key] = RuntimeError("boom")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert d.values["front"]
    assert set(d.missing) == {"translate", "pos", "ipa", "meaning", "sound"}
    assert d.errors and all("внутренняя ошибка" in e for e in d.errors)
    assert not any("boom" in e for e in d.errors)


def test_failed_lookup_gives_one_error_two_missing(src):
    src["dict"] = SourceError("нет связи")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert "pos" in d.missing and "ipa" in d.missing
    assert len(d.errors) == 1


def test_empty_pos_is_missing(src):
    src["dict"] = WordData([Role("", "ɡɪv", "def")])
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert d.values["pos"] == "" and d.missing == ["pos"]
    assert d.values["ipa"] == "ɡɪv"


def test_sources_receive_right_arguments(src):
    st = Settings(deepl_key="KEY", tts_lang="en-US")
    build_draft("give up", occ_for("give up"), st)
    c = src["calls"]
    assert c["tr"][0] == (SENT, "KEY")
    assert c["mean"][0] == ("give up", "KEY")
    assert c["audio"][0] == ("give up", "en-US")
    assert "dict" not in c


def test_malformed_word_data_is_isolated(src):
    src["dict"] = object()
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert {"pos", "ipa"} <= set(d.missing)
    assert d.values["front"] and d.values["sound"]


def test_none_word_data_is_missing(src):
    src["dict"] = None
    d = build_draft("smoking", occ_for("smoking"), Settings())
    resolve_choices(d)
    assert {"pos", "ipa"} <= set(d.missing) and len(d.errors) == 1


def test_unexpected_exception_is_logged(src, caplog):
    src["tr"] = RuntimeError("boom")
    build_draft("smoking", occ_for("smoking"), Settings())
    assert any(r.exc_info and "boom" in str(r.exc_info[1]) for r in caplog.records)


def test_sound_not_requested_when_unmapped(src):
    d = build_draft("smoking", occ_for("smoking"), Settings(), want_sound=False)
    assert "audio" not in src["calls"] and d.audio is None and "sound" not in d.missing


def test_deepl_fallback_note_reaches_draft_warnings(src):
    src["tr"] = translate.Translation("Привет", "google", "DeepL отказал (403)")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.warnings == ["DeepL отказал (403)"]
