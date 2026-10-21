import pytest

from anki_sentence_cards import card
from anki_sentence_cards.book.search import Occurrence
from anki_sentence_cards.card import build_draft
from anki_sentence_cards.settings import Settings
from anki_sentence_cards.sources import dictionary, meaning, translate, tts
from anki_sentence_cards.sources.dictionary import DictEntry
from anki_sentence_cards.sources.http import SourceError
from anki_sentence_cards.sources.meaning import Meaning

SENT = "He had to give up smoking."
KEYS = {"front", "translate", "pos", "ipa", "meaning", "sound"}


def occ_for(form):
    i = SENT.index(form)
    return Occurrence(0, SENT, form, i, i + len(form), True)


@pytest.fixture
def src(monkeypatch):
    s = {"tr": translate.Translation("Ему пришлось бросить курить.", "google"),
         "dict": DictEntry("verb", "ɡɪv", "stop doing"),
         "mean": Meaning("(verb) stop - бросить", "reverso"),
         "audio": b"MP3DATA", "lookups": []}

    def pick(key):
        v = s[key]
        if isinstance(v, Exception):
            raise v
        return v

    def lookup(word):
        s["lookups"].append(word)
        return pick("dict")

    monkeypatch.setattr(translate, "translate", lambda text, key, target="RU": pick("tr"))
    monkeypatch.setattr(dictionary, "lookup", lookup)
    monkeypatch.setattr(meaning, "get_meaning", lambda w, k, e: pick("mean"))
    monkeypatch.setattr(tts, "synthesize", lambda w, lang="en-GB": pick("audio"))
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


def test_dictionary_failure_still_gives_meaning_with_no_entry(src, monkeypatch):
    seen = []
    src["dict"] = SourceError("нет")
    monkeypatch.setattr(meaning, "get_meaning", lambda w, k, e: seen.append(e) or Meaning("m", "x"))
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert seen == [None] and d.values["meaning"] == "m"


def test_empty_ipa_is_missing_but_pos_kept(src):
    src["dict"] = DictEntry("verb", "", "def")
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert d.values["pos"] == "verb" and d.values["ipa"] == ""
    assert d.missing == ["ipa"] and d.errors


def test_blank_results_are_not_passed_as_success(src):
    src["tr"] = translate.Translation("  ", "google")
    src["mean"] = Meaning("", "x")
    src["audio"] = b""
    d = build_draft("smoking", occ_for("smoking"), Settings())
    assert set(d.missing) == {"translate", "meaning", "sound"}
    assert d.values["sound"] == "" and d.audio is None


def test_card_module_is_importable_without_anki():
    assert hasattr(card, "CardDraft")
