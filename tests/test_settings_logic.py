from anki_sentence_cards.notes import mappable_fields, plan_field_map, resolve_field_map
from anki_sentence_cards.settings import (
    NOT_FILLED, Settings, add_book, build_field_map, load_settings, merge_for_save,
    normalize_active, remove_book, to_dict,
)


def test_merge_keeps_unknown_keys_and_new_values_win():
    raw = {"deck": "Old", "my_hand_edit": 1}
    out = merge_for_save(raw, Settings(deck="New"))
    assert out["my_hand_edit"] == 1
    assert out["deck"] == "New"


def test_merge_does_not_mutate_raw():
    raw = {"deck": "Old"}
    merge_for_save(raw, Settings(deck="New"))
    assert raw == {"deck": "Old"}


def test_add_book_normalizes_and_dedupes():
    books = add_book([], "/a/b/../c.txt")
    assert books == ["/a/c.txt"]
    assert add_book(books, "/a/c.txt") == books
    assert add_book(books, "  ") == books


def test_add_book_does_not_mutate():
    books = ["/x.txt"]
    add_book(books, "/y.txt")
    assert books == ["/x.txt"]


def test_remove_inactive_book_keeps_active():
    assert remove_book(["/a", "/b"], "/a", "/b") == (["/a"], "/a")


def test_remove_active_book_picks_first_remaining():
    assert remove_book(["/a", "/b"], "/a", "/a") == (["/b"], "/b")


def test_remove_last_book_clears_active():
    assert remove_book(["/a"], "/a", "/a") == ([], "")


def test_first_book_added_is_not_auto_active_by_add_book_alone():
    # add_book only manages the list; activation is the caller's rule
    assert add_book([], "/a.txt") == ["/a.txt"]


def test_mappable_fields_drops_excluded():
    got = mappable_fields(["Front", "Sound of sentence", "Notes", "Meaning"])
    assert got == ["Front", "Meaning"]


def test_build_field_map_keeps_not_filled_explicit():
    m, ok = build_field_map({"front": "Front", "ipa": NOT_FILLED, "pos": "Type"})
    assert m == {"front": "Front", "ipa": "", "pos": "Type"}
    assert ok is True


def test_build_field_map_requires_front():
    assert build_field_map({"front": NOT_FILLED, "pos": "Type"})[1] is False
    assert build_field_map({"pos": "Type"})[1] is False


FIELDS = ["Front", "Translate", "Type of word", "Transcription of word", "Meaning", "Sound of word"]


def test_not_filled_survives_save_and_reload():
    m, _ = build_field_map({"front": "Front", "translate": NOT_FILLED})
    s = load_settings(merge_for_save({}, Settings(field_map=m)))
    resolved, unresolved = resolve_field_map(FIELDS, s.field_map)
    assert "translate" not in resolved      # default name exists, still disabled
    assert "translate" not in unresolved
    assert resolved["front"] == "Front"


def test_plan_keeps_map_for_same_notetype_even_when_first_run():
    saved = {"front": "Front", "ipa": ""}
    keep, unresolved = plan_field_map(FIELDS, saved, "A", "A")
    assert keep == saved and unresolved == []


def test_plan_manual_map_on_first_run_not_wiped():
    # first run: settings notetype is "", user picks A, maps manually,
    # caller records map_notetype = A, then saves
    saved = {"front": "Front"}
    keep, _ = plan_field_map(FIELDS, saved, "A", "A")
    assert keep == saved


def test_plan_drops_map_of_other_notetype():
    keep, _ = plan_field_map(FIELDS, {"front": "Zzz"}, "A", "B")
    assert keep == {}


def test_plan_reports_unresolved_front():
    _, unresolved = plan_field_map(["Other"], {}, "A", "A")
    assert "front" in unresolved


def test_load_settings_survives_garbage():
    s = load_settings({"occurrence_limit": "abc", "books": None, "tts_lang": "fr",
                       "field_map": [1], "deck": 5, "deepl_key": None})
    assert (s.occurrence_limit, s.books, s.tts_lang, s.field_map, s.deck, s.deepl_key) == (50, [], "en-GB", {}, "", "")


def test_load_settings_filters_books_and_non_dict():
    assert load_settings({"books": ["a", 3, None, ""]}).books == ["a"]
    assert load_settings(None) == Settings()
    assert load_settings({"occurrence_limit": None}).occurrence_limit == 50
    assert load_settings({"occurrence_limit": "7"}).occurrence_limit == 7
    assert load_settings({"occurrence_limit": -3}).occurrence_limit == 50


def test_normalize_active():
    assert normalize_active(["a", "b"], "b") == "b"
    assert normalize_active(["a", "b"], "zz") == "a"
    assert normalize_active([], "zz") == ""
