from anki_sentence_cards.book.search import find_occurrences, mark_match, word_forms


def test_exact_form_comes_first():
    assert word_forms("Carry")[0] == "carry"


def test_regular_inflections_found():
    assert "carried" in word_forms("carry")
    assert "running" in word_forms("run")
    assert "walked" in word_forms("walk")
    assert "boxes" in word_forms("box")


def test_reverse_forms_for_inflected_input():
    assert "carry" in word_forms("carried")
    assert "run" in word_forms("running")
    assert "walk" in word_forms("walks")


def test_word_boundaries_respected():
    occ, _ = find_occurrences(["I can swim.", "A candle burned."], "can", 50)
    assert len(occ) == 1


def test_apostrophe_word_is_not_matched():
    occ, _ = find_occurrences(["I can't swim."], "can", 50)
    assert occ == []


def test_capitalized_at_sentence_start_is_found():
    occ, _ = find_occurrences(["Run fast."], "run", 50)
    assert len(occ) == 1 and occ[0].matched_form == "Run"


def test_exact_flag_and_indexes():
    occ, _ = find_occurrences(["x.", "He ran home.", "I run."], "run", 50)
    assert [o.sentence_index for o in occ] == [1, 2]
    assert [o.exact for o in occ] == [False, True]


def test_phrase_query_inflects_first_word():
    occ, _ = find_occurrences(["He gave up."], "give up", 50)
    assert occ[0].matched_form == "gave up"


def test_phrase_allows_any_whitespace():
    occ, _ = find_occurrences(["He gave\n  up."], "give up", 50)
    assert len(occ) == 1


def test_limit_sets_truncated_flag():
    occ, truncated = find_occurrences(["the cat."] * 100, "cat", 10)
    assert len(occ) == 10 and truncated is True


def test_not_truncated_when_within_limit():
    occ, truncated = find_occurrences(["the cat."] * 3, "cat", 10)
    assert len(occ) == 3 and truncated is False


def test_mark_match_wraps_found_form():
    occ, _ = find_occurrences(["He gave up."], "give up", 50)
    assert mark_match(occ[0]) == "He <b>gave up</b>."
