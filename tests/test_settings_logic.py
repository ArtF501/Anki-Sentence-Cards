from anki_sentence_cards.notes import mappable_fields, settle_field_map, resolve_field_map
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
    m, ok, _c = build_field_map({"front": "Front", "ipa": NOT_FILLED, "pos": "Type"})
    assert m == {"front": "Front", "ipa": "", "pos": "Type"}
    assert ok is True


def test_build_field_map_requires_front():
    assert build_field_map({"front": NOT_FILLED, "pos": "Type"})[1] is False
    assert build_field_map({"pos": "Type"})[1] is False


FIELDS = ["Front", "Translate", "Type of word", "Transcription of word", "Meaning", "Sound of word"]


def test_not_filled_survives_save_and_reload():
    m, _, _c = build_field_map({"front": "Front", "translate": NOT_FILLED})
    s = load_settings(merge_for_save({}, Settings(field_map=m)))
    resolved, unresolved = resolve_field_map(FIELDS, s.field_map)
    assert "translate" not in resolved      # default name exists, still disabled
    assert "translate" not in unresolved
    assert resolved["front"] == "Front"


MAP_A = {"front": "Front", "ipa": ""}


def test_settle_cancel_on_other_type_keeps_all_maps():
    maps = {"A": MAP_A}
    out = settle_field_map(["Other"], maps, "B", True, lambda cur: None)
    assert out == {"A": MAP_A}          # back to A: map still there


def test_settle_choice_stored_for_that_type_only():
    out = settle_field_map(FIELDS, {"A": MAP_A}, "B", True, lambda cur: {"front": "Front"})
    assert out == {"A": MAP_A, "B": {"front": "Front"}}


def test_settle_first_run_manual_map_kept():
    out = settle_field_map(FIELDS, {}, "A", True, lambda cur: {"front": "Front"})
    assert out["A"] == {"front": "Front"}


def test_settle_no_prompt_when_resolved_and_not_forced():
    def boom(cur):
        raise AssertionError("must not ask")
    assert settle_field_map(FIELDS, {"A": MAP_A}, "A", False, boom) == {"A": MAP_A}


def test_settle_prompts_on_unresolved_and_passes_current():
    seen = []
    settle_field_map(["Other"], {"A": MAP_A}, "A", False, lambda cur: seen.append(cur))
    assert seen == [MAP_A]


def test_settle_does_not_mutate_input():
    maps = {"A": MAP_A}
    settle_field_map(FIELDS, maps, "B", True, lambda cur: {"front": "Front"})
    assert maps == {"A": MAP_A}


def test_load_settings_infinite_limit():
    assert load_settings({"occurrence_limit": float("inf")}).occurrence_limit == 50


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


def test_build_field_map_detects_collision():
    _, ok, collision = build_field_map({"front": "Front", "meaning": "Meaning", "pos": "Meaning"})
    assert ok and collision


def test_build_field_map_empty_choices_are_not_a_collision():
    assert build_field_map({"front": "Front", "ipa": NOT_FILLED, "pos": NOT_FILLED})[2] is False
