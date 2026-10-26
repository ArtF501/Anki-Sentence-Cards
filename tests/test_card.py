import pytest

from anki_sentence_cards import card
from anki_sentence_cards.book.search import Occurrence
from anki_sentence_cards.card import build_draft
from anki_sentence_cards.settings import Settings
from anki_sentence_cards.sources import dictionary, meaning, translate, tts
from anki_sentence_cards.sources.roles import Role, WordData
from anki_sentence_cards.sources.http import SourceError
from anki_sentence_cards.sources.meaning import MeaningOption

SENT = "He had to give up smoking."
KEYS = {"front", "translate", "pos", "ipa", "meaning", "sound"}


def occ_for(form):
    i = SENT.index(form)
    return Occurrence(0, SENT, form, i, i + len(form), True)


@pytest.fixture
def src(monkeypatch):
    s = {"tr": translate.Translation("Ему пришлось бросить курить.", "google"),
         "dict": WordData([Role("verb", "ɡɪv", "stop doing")]),
         "mean": [MeaningOption("", "бросить", "reverso")],
         "audio": b"MP3DATA", "lookups": []}

    def pick(key):
        v = s[key]
        if isinstance(v, Exception):
            raise v
        return v

    def lookup(word):
        s["lookups"].append(word)
        return pick("dict")

    s["calls"] = {}

    def rec(name, fn):
        def w(*args, **kw):
            s["calls"][name] = (args, kw)
            return fn(*args, **kw)
        return w

    monkeypatch.setattr(translate, "translate", rec("tr", lambda text, key, target="RU": pick("tr")))
    monkeypatch.setattr(dictionary, "lookup", rec("dict", lookup))
    monkeypatch.setattr(meaning, "get_meaning_options", rec("mean", lambda w, k: pick("mean")))
    monkeypatch.setattr(tts, "synthesize", rec("audio", lambda w, lang="en-GB": pick("audio")))
    return s


def test_front_contains_bolded_form(src):
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.values["front"] == "He had to give up <b>smoking</b>."
    assert set(d.values) == KEYS
    assert d.missing == [] and d.errors == []
    assert d.values["pos"] == "verb" and d.values["ipa"] == "ɡɪv"


def test_sound_field_is_anki_sound_tag(src):
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.values["sound"] == "[sound:%s]" % d.audio_name
    assert d.audio == b"MP3DATA" and d.audio_name.endswith(".mp3")


def test_phrase_skips_dictionary_and_sets_pos_phrase(src):
    d = build_draft("give up", occ_for("give up"), Settings())
    assert d.values["pos"] == "phrase" and d.values["ipa"] == ""
    assert src["lookups"] == []
    assert "pos" not in d.missing and "ipa" not in d.missing


def test_failed_source_leaves_field_empty_and_records_it(src):
    src["tr"] = SourceError("DeepL недоступен")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert "translate" in d.missing and d.values["translate"] == ""


def test_one_dead_source_does_not_stop_the_others(src):
    src["tr"] = SourceError("x")
    src["dict"] = SourceError("y")
    src["audio"] = SourceError("z")
    d = build_draft("smoking", occ_for("smoking"), Settings())
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
    assert d.values["meaning"] == "" and "meaning" in d.missing
    assert d.values["translate"] and d.values["sound"]


def test_dictionary_failure_leaves_the_meaning_without_an_english_part(src):
    src["dict"] = SourceError("нет")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.values["meaning"] == "бросить"


def test_empty_ipa_is_missing_but_pos_kept(src):
    src["dict"] = WordData([Role("verb", "", "def")])
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.values["pos"] == "verb" and d.values["ipa"] == ""
    assert d.missing == ["ipa"] and d.errors


def test_blank_results_are_not_passed_as_success(src):
    src["tr"] = translate.Translation("  ", "google")
    src["mean"] = [MeaningOption("", "  ", "reverso")]
    src["audio"] = b""
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert set(d.missing) == {"translate", "meaning", "sound"}
    assert d.values["sound"] == "" and d.audio is None


def test_unexpected_exception_is_isolated(src):
    for key in ("tr", "dict", "mean", "audio"):
        src[key] = RuntimeError("boom")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.values["front"]
    assert set(d.missing) == {"translate", "pos", "ipa", "meaning", "sound"}
    assert d.errors and all("внутренняя ошибка" in e for e in d.errors)
    assert not any("boom" in e for e in d.errors)


def test_failed_lookup_gives_one_error_two_missing(src):
    src["dict"] = SourceError("нет связи")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert "pos" in d.missing and "ipa" in d.missing
    assert len(d.errors) == 1


def test_empty_pos_is_missing(src):
    src["dict"] = WordData([Role("", "ɡɪv", "def")])
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.values["pos"] == "" and d.missing == ["pos"]


def test_sources_receive_right_arguments(src):
    st = Settings(deepl_key="KEY", tts_lang="en-US")
    build_draft("give up", occ_for("give up"), st)
    c = src["calls"]
    assert c["tr"][0] == (SENT, "KEY")
    assert c["mean"][0] == ("give up", "KEY")
    assert c["audio"][0] == ("give up", "en-US")
    assert "dict" not in c


def test_malformed_dict_entry_is_isolated(src):
    src["dict"] = object()
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert {"pos", "ipa"} <= set(d.missing)
    assert d.values["front"] and d.values["sound"]


def test_none_dict_entry_is_missing(src):
    src["dict"] = None
    d = build_draft("smoking", occ_for("smoking"), Settings())
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
