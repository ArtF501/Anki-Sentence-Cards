from anki_sentence_cards.book.sentences import split_sentences


def test_abbreviation_does_not_split_sentence():
    assert len(split_sentences("Mr. Angier left. He returned.")) == 2


def test_st_etc_and_initials_do_not_split():
    assert split_sentences("J. R. Smith lived on St. Mary Street. He left.") == [
        "J. R. Smith lived on St. Mary Street.",
        "He left.",
    ]
    assert len(split_sentences("Dr. Brown sold pears, etc. and plums. Done.")) == 2


def test_quoted_sentence_stays_whole():
    assert split_sentences('"You can\'t stay," he said. "It is late."') == [
        '"You can\'t stay," he said.',
        '"It is late."',
    ]


def test_closing_quote_goes_with_its_sentence():
    assert split_sentences('He said "go." Then he left.') == ['He said "go."', "Then he left."]


def test_question_inside_quote_followed_by_lowercase_does_not_split():
    assert split_sentences('"Who gives up first?" asked Smith. He did.') == [
        '"Who gives up first?" asked Smith.',
        "He did.",
    ]


def test_paragraph_boundary_splits_without_terminator():
    assert split_sentences("A heading\n\nBody text here.") == ["A heading", "Body text here."]


def test_empty():
    assert split_sentences("") == []


def test_dialogue_ending_in_no_splits():
    assert split_sentences('"I said no." He left.') == ['"I said no."', "He left."]


def test_no_before_capital_splits():
    assert split_sentences("Oh, no. He left.") == ["Oh, no.", "He left."]


def test_etc_before_capital_splits():
    assert split_sentences("He left, etc. Then he returned.") == ["He left, etc.", "Then he returned."]


def test_ordinal_1st_is_not_st_abbreviation():
    assert split_sentences("on the 1st. Then he left.") == ["on the 1st.", "Then he left."]


def test_titles_are_case_sensitive():
    assert split_sentences("He met dr. Then he left.") == ["He met dr.", "Then he left."]
