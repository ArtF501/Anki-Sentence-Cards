from anki_sentence_cards.notes import mappable_fields
from anki_sentence_cards.settings import (
    NOT_FILLED, Settings, add_book, build_field_map, merge_for_save, remove_book,
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


def test_build_field_map_skips_not_filled():
    m, ok = build_field_map({"front": "Front", "ipa": NOT_FILLED, "pos": "Type"})
    assert m == {"front": "Front", "pos": "Type"}
    assert ok is True


def test_build_field_map_requires_front():
    assert build_field_map({"front": NOT_FILLED, "pos": "Type"})[1] is False
    assert build_field_map({"pos": "Type"})[1] is False
