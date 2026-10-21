from anki_sentence_cards.settings import load_settings, to_dict


def test_defaults_when_config_empty():
    s = load_settings({})
    assert s.tts_lang == "en-GB"
    assert s.occurrence_limit == 50
    assert s.field_map == {}


def test_roundtrip_preserves_unknown_safe_fields():
    s = load_settings({"deepl_key": "abc", "tts_lang": "en-US"})
    assert to_dict(s)["deepl_key"] == "abc"
    assert to_dict(s)["tts_lang"] == "en-US"
