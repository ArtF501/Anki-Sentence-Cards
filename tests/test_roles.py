from anki_sentence_cards.sources.roles import Role, WordData, merge_roles, order_roles


def test_merge_roles_collapses_repeated_pos():
    rs = [Role("verb", "", "to go"), Role("noun", "", "a go"), Role("verb", "rʌn", "")]
    out = merge_roles(rs)
    assert [r.pos for r in out] == ["verb", "noun"]
    assert out[0].definition == "to go"      # первое определение сохраняется
    assert out[0].ipa == "rʌn"               # непустое поле добирается из повтора


def test_merge_roles_keeps_same_pos_from_different_lemmas():
    rs = [Role("verb", lemma=""), Role("verb", lemma="supervise")]
    assert len(merge_roles(rs)) == 2


def test_order_roles_puts_lemma_roles_last():
    rs = [Role("noun", lemma="tire"), Role("adjective", lemma="")]
    assert [r.pos for r in order_roles(rs)] == ["adjective", "noun"]


def test_word_data_defaults_are_empty():
    d = WordData()
    assert d.roles == [] and d.shared_ipa == ""
