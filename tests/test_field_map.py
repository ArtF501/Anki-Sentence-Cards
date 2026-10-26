from anki_sentence_cards.notes import DEFAULT_FIELD_NAMES, resolve_field_map, note_tags, escape_search, sync_sound_name, check_front, NoteError, NoteTypeMissing, DuplicateCheckFailed
from anki_sentence_cards.card import CardDraft
import pytest

ALL = ["Front", "Sound of sentence", "Translate", "Type of word",
       "Transcription of word", "Sound of word", "Meaning", "Notes"]


def test_default_names_mapped_automatically():
    m, unresolved = resolve_field_map(list(DEFAULT_FIELD_NAMES.values()), {})
    assert unresolved == []
    assert m == DEFAULT_FIELD_NAMES


def test_logical_keys_are_the_fixed_set():
    assert set(DEFAULT_FIELD_NAMES) == {"front", "translate", "pos", "ipa", "meaning", "sound"}


def test_case_and_space_insensitive_fallback():
    m, unresolved = resolve_field_map(["front", "TRANSLATE", "Type  of word", "transcriptionofword",
                                       "Sound of Word", "meaning"], {})
    assert unresolved == []
    assert m["front"] == "front" and m["ipa"] == "transcriptionofword"


def test_saved_map_wins_over_defaults():
    m, unresolved = resolve_field_map(ALL + ["Definition"], {"meaning": "Definition"})
    assert m["meaning"] == "Definition"
    assert unresolved == []


def test_saved_name_gone_from_notetype_falls_back_to_default():
    m, _ = resolve_field_map(ALL, {"meaning": "Deleted field"})
    assert m["meaning"] == "Meaning"


def test_missing_field_reported_as_unresolved():
    m, unresolved = resolve_field_map(["Front", "Back"], {})
    assert "meaning" in unresolved
    assert "front" not in unresolved and "front" in m


def test_sound_of_sentence_and_notes_never_in_map():
    m, _ = resolve_field_map(ALL, {"front": "Notes", "sound": "Sound of sentence"})
    assert "Sound of sentence" not in m.values()
    assert "Notes" not in m.values()
    assert m["front"] == "Front" and m["sound"] == "Sound of word"


def test_tags():
    assert note_tags([]) == ["asc"]
    assert note_tags(["meaning"]) == ["asc", "auto-incomplete"]


def test_escape_search():
    assert escape_search('a\\b') == 'a\\\\b'
    assert escape_search('say "hi"') == 'say \\"hi\\"'
    assert escape_search("foo:bar*_") == "foo\\:bar\\*\\_"
    assert escape_search("plain") == "plain"


def test_sync_sound_name():
    v = {"sound": "[sound:a.mp3]"}
    sync_sound_name(v, "a.mp3", "a_1.mp3")
    assert v["sound"] == "[sound:a_1.mp3]"
    sync_sound_name(v, "a_1.mp3", "a_1.mp3")
    assert v["sound"] == "[sound:a_1.mp3]"


def _draft(front):
    return CardDraft(word="w", values={"front": front})


def test_check_front():
    check_front(_draft("a *w* b"), {"front": "Front"})
    with pytest.raises(NoteError):
        check_front(_draft("a"), {})
    with pytest.raises(NoteError):
        check_front(_draft("  "), {"front": "Front"})


def test_note_type_missing_is_note_error():
    assert issubclass(NoteTypeMissing, NoteError)


def test_check_front_markup_only_is_empty():
    for v in ("<b></b>", "<br>", "&nbsp;", " <div><br></div> "):
        with pytest.raises(NoteError):
            check_front(_draft(v), {"front": "Front"})


def test_duplicate_check_failed_is_note_error_not_type_missing():
    assert issubclass(DuplicateCheckFailed, NoteError)
    assert not issubclass(DuplicateCheckFailed, NoteTypeMissing)
