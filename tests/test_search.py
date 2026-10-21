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


def _n(sents, q):
    return len(find_occurrences(sents, q, 50)[0])


def test_quoted_words_and_possessives_found():
    assert _n(["He said 'can you swim' loudly."], "can") == 1
    assert _n(["'I will run'"], "run") == 1
    assert _n(["the cat's tail"], "cat") == 1
    assert _n(["It is six o'clock."], "clock") == 0
    assert _n(["I can't swim."], "can") == 0


def test_no_foreign_words_from_bad_candidates():
    assert _n(["The seed grew."], "see") == 0
    assert _n(["Something new."], "news") == 0
    assert _n(["Even so."], "evening") == 0
    assert _n(["A wick burned."], "wicked") == 0


def test_irregular_verbs():
    assert _n(["He told me."], "tell") == 1
    assert _n(["She felt cold."], "feel") == 1
    assert _n(["I am here."], "be") == 1
    assert _n(["He sat down."], "sit") == 1


def test_exact_form_preferred_within_sentence():
    occ, _ = find_occurrences(["He ran and I run."], "run", 50)
    assert occ[0].matched_form == "run" and occ[0].exact is True


def test_reverse_forms_from_printed_inflection():
    for inflected, base in [
        ("making", "make"), ("taking", "take"), ("using", "use"),
        ("loved", "love"), ("liked", "like"), ("cats", "cat"),
        ("dogs", "dog"), ("boxes", "box"), ("tries", "try"),
        ("tied", "tie"), ("dies", "die"), ("sees", "see"),
    ]:
        assert base in word_forms(inflected), (inflected, base)


def test_reverse_forms_find_sentences():
    assert _n(["a cat sat"], "cats") == 1
    assert _n(["she love it"], "loved") == 1
    assert _n(["He is make it."], "making") == 1


def test_mark_match_without_match_has_no_empty_bold():
    from anki_sentence_cards.book.search import Occurrence, mark_match
    assert mark_match(Occurrence(0, "Nothing here.", "", 0, 0, False)) == "Nothing here."
