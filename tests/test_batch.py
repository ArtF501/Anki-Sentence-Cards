import threading
import time
from types import SimpleNamespace

from anki_sentence_cards import batch as b
from anki_sentence_cards.book.search import Occurrence, find_occurrences, mark_match
from anki_sentence_cards.card import CardDraft
from anki_sentence_cards.sources.meaning import MeaningOption
from anki_sentence_cards.sources.roles import Role
from anki_sentence_cards.notes import (DuplicateCheckFailed, NoteError, NoteTypeMissing,
                                       add_note, DEFAULT_FIELD_NAMES)


def occ(s="He was reluctant to go."):
    return find_occurrences([s], "reluctant", 5)[0][0]


def draft(word="w", missing=(), errors=()):
    return CardDraft(word, {"front": "x <b>w</b>", "translate": "", "pos": "", "ipa": "",
                            "meaning": "", "sound": ""}, missing=list(missing), errors=list(errors))


def test_parse_words():
    assert b.parse_words("a\n\n  b  c \nA\n b C\n") == ["a", "b c"]


def test_manual_occurrence_with_and_without_word():
    o = b.manual_occurrence("reluctant", "He was  reluctant.")
    assert mark_match(o) == "He was <b>reluctant</b>."
    o = b.manual_occurrence("reluctant", "Nothing here.")
    assert "<b>" not in b.highlight_html(o)


def test_highlight_escapes():
    o = find_occurrences(["a <i> reluctant & b"], "reluctant", 1)[0][0]
    assert b.highlight_html(o) == "a &lt;i&gt; <b>reluctant</b> &amp; b"


def test_limit_note():
    assert b.limit_note(3, False, 3) == ""
    assert "3" in b.limit_note(3, True, 3)


def test_pick_state_walk():
    st = b.PickState(["a", "b", "c"])
    assert st.counter == "1 из 3"
    st.choose(occ())
    assert st.counter == "2 из 3"
    assert not st.choose_manual("   ")
    assert st.current == "b"
    st.skip()
    assert st.choose_manual("see c here")
    assert st.done and st.current is None
    assert [p.word for p in st.picks] == ["a", "c"] and st.skipped == ["b"]
    st.skip()  # no-op when done
    assert st.skipped == ["b"]


S = SimpleNamespace


def test_preflight():
    ok = S(active_book="x", deck="D", notetype="N", field_map={})
    f = list(DEFAULT_FIELD_NAMES.values())
    assert b.preflight(ok, f, True).fatal == "" and b.preflight(ok, f, True).field_map["front"] == "Front"
    assert b.preflight(S(**{**ok.__dict__, "active_book": ""}), f, True).fatal
    assert b.preflight(ok, f, False).fatal
    assert b.preflight(S(**{**ok.__dict__, "deck": ""}), f, True).fatal
    assert b.preflight(ok, None, True).fatal
    assert b.preflight(ok, ["Back"], True).fatal  # front unresolved
    p = b.preflight(ok, ["Front"], True)  # others unresolved: warning only
    assert p.fatal == "" and len(p.warnings) == 1
    # explicit not-filled is not a warning
    no = S(**{**ok.__dict__, "field_map": {k: "" for k in DEFAULT_FIELD_NAMES if k != "front"}})
    assert b.preflight(no, ["Front"], True).warnings == []


class FakeCol:
    """Just enough of the collection for the real notes.add_note."""
    def __init__(self, has_type=True, existing=(), fail_find=False, reject=()):
        self.has_type, self.existing, self.fail_find, self.reject = has_type, list(existing), fail_find, reject
        self.added = []
        self.models = S(by_name=lambda n: {} if self.has_type else None)
        self.decks = S(id=lambda n: 1)
        self.media = S(write_data=lambda n, d: n)

    def new_note(self, model):
        class N(dict):
            id = 7
            tags = []
            def add_tag(self, t): self.tags.append(t)
        return N()

    def add_note(self, note, deck):
        if note["Front"] in self.reject:
            raise RuntimeError("bad")
        self.added.append(note)

    def find_notes(self, q):
        if self.fail_find:
            raise RuntimeError("search broke")
        return [n for n in self.existing if '"%s"' % n in q]

    def get_note(self, nid):
        return S(fields=[nid])


def sync_bg(work, ok, fail):
    try:
        v = work()
    except Exception as e:
        fail(e)
        return
    ok(v)


def run(words, col, builder=None, field_map=None, run_bg=sync_bg):
    """Calls batch.run_batch, the very function the dialog calls."""
    from anki_sentence_cards.notes import find_duplicate
    fmap = field_map or {"front": "Front"}
    picks = [b.Pick(w, occ()) for w in words]
    res = b.BatchResult()
    seen = []
    b.run_batch(picks, lambda w: find_duplicate(col, "D", w), builder or (lambda w, o: draft(w)),
                lambda d: add_note(col, d, "D", "N", fmap), res, run_bg, seen.append)
    assert seen == [res]  # done called exactly once
    return res


def status(res):
    return {o.word: o.status for o in res.outcomes}


def test_pipeline_happy_and_incomplete():
    col = FakeCol()
    res = run(["a", "b"], col, lambda w, o: draft(w, ["ipa"], ["x"]) if w == "b" else draft(w))
    assert status(res) == {"a": b.CREATED, "b": b.INCOMPLETE}
    assert len(col.added) == 2
    assert res.outcomes[1].reasons == ["x"]


def test_pipeline_duplicate_not_created():
    col = FakeCol(existing=["dup"])
    res = run(["dup", "new"], col)
    assert status(res) == {"dup": b.DUPLICATE, "new": b.CREATED}
    assert len(col.added) == 1


def test_pipeline_dup_check_broken_warns_once_and_words_not_failed():
    col = FakeCol(fail_find=True)
    res = run(["a", "b", "c"], col)
    assert set(status(res).values()) == {b.CREATED}
    assert len(res.warnings) == 1 and len(col.added) == 3


def test_pipeline_note_error_marks_word_and_continues():
    bad = lambda w, o: draft(w) if w != "a" else CardDraft("a", {"front": "<b></b>"})
    res = run(["a", "b"], FakeCol(), bad)
    assert status(res) == {"a": b.FAILED, "b": b.CREATED}
    assert "лицев" in res.outcomes[0].reasons[0]


def test_pipeline_non_noteerror_exception_marks_word_and_continues():
    col = FakeCol()
    calls = []

    def decks_id(name):
        calls.append(name)
        if len(calls) == 1:
            raise ValueError("deck broke")
        return 1
    col.decks = S(id=decks_id)
    res = run(["a", "b"], col)
    assert status(res) == {"a": b.FAILED, "b": b.CREATED}
    assert "deck broke" in res.outcomes[0].reasons[0]


def test_background_failure_leaves_words_retryable():
    def bg(work, ok, fail):
        fail(RuntimeError("boom"))
    res = run(["a", "b"], FakeCol(), run_bg=bg)
    assert set(status(res).values()) == {b.NOT_PROCESSED}
    assert b.retry_words(res.outcomes) == ["a", "b"] and res.warnings


def test_merge_results_keeps_earlier_run():
    prev = b.BatchResult([b.Outcome("a", b.CREATED), b.Outcome("d", b.FAILED, ["x"])], ["w1"])
    new = b.BatchResult([b.Outcome("d", b.CREATED)], ["w2"])
    m = b.merge_results(prev, new, ["d"])
    assert status(m) == {"a": b.CREATED, "d": b.CREATED} and m.warnings == ["w1", "w2"]


def test_pipeline_notetype_missing_stops_batch():
    col = FakeCol(has_type=False)
    res = run(["a", "b", "c"], col)
    assert set(status(res).values()) == {b.NOT_PROCESSED}
    assert len(res.outcomes) == 3 and len(res.warnings) == 1
    assert b.retry_words(res.outcomes) == ["a", "b", "c"]


def test_build_exception_is_a_failed_word_not_a_crash():
    def boom(w, o):
        if w == "a":
            raise ValueError("x")
        return draft(w)
    res = run(["a", "b"], FakeCol(), boom)
    assert status(res) == {"a": b.FAILED, "b": b.CREATED}


def test_build_progress_reported():
    seen = []
    b.build_drafts([b.Pick("a", occ()), b.Pick("b", occ())], lambda w, o: draft(w),
                   lambda i, n, w: seen.append((i, n, w)))
    assert seen == [(0, 2, "a"), (1, 2, "b")]


def test_report_groups_and_retry():
    outs = [b.Outcome("a", b.CREATED), b.Outcome("b", b.INCOMPLETE, ["нет озвучки"]),
            b.Outcome("c", b.DUPLICATE, ["уже есть"]), b.Outcome("d", b.FAILED, ["плохо"]),
            b.Outcome("e", b.NOT_PROCESSED, ["стоп"])]
    g = b.group_report(outs)
    assert [o.word for o in g["created"]] == ["a"]
    assert [o.word for o in g["incomplete"]] == ["b"]
    assert [o.word for o in g["not_created"]] == ["c", "d", "e"]
    assert b.retry_words(outs) == ["d", "e"]
    text = dict(b.report_text(outs))
    assert text["Создано с пустыми полями (1)"] == ["b — нет озвучки"]
    assert len(text) == 3
    assert b.report_text([b.Outcome("a", b.CREATED)]) == [("Создано (1)", ["a"])]


def test_retry_goes_back_to_picking_only_with_problem_words():
    outs = [b.Outcome("a", b.CREATED), b.Outcome("d", b.FAILED, ["x"])]
    st = b.PickState(b.retry_words(outs))
    assert st.words == ["d"]


def test_parse_words_strips_numbering_and_edge_punctuation():
    assert b.parse_words("1. reluctant\nreluctant,\n2) give up;\n- “odd”\n") == ["reluctant", "give up", "odd"]


def test_manual_occurrence_normalizes_curly_apostrophe():
    occ = b.manual_occurrence("don't", "I don’t know.")
    assert b.highlight_html(occ) == "I <b>don&#x27;t</b> know."


# ---------------------------------------------------------------- choice pass

def choice_draft(roles=("verb",), meanings=1, definitions=None, shared_ipa="", word="x"):
    defs = list(definitions or [""] * len(roles))
    d = CardDraft(word=word,
                  values={k: "" for k in ("front", "translate", "pos", "ipa", "meaning", "sound")})
    d.roles = [Role(pos, "", defs[i]) for i, pos in enumerate(roles)]
    d.shared_ipa = shared_ipa
    d.meanings = [MeaningOption("", "перевод%d" % i, "reverso") for i in range(meanings)]
    return d


# Review Focus 5
def test_choice_a_word_with_one_role_and_one_meaning_is_not_asked():
    assert b.needs_choice(choice_draft(roles=["verb"], meanings=1)) is False


def test_choice_four_roles_and_one_meaning_asks_only_the_role():
    st = b.ChoiceState([choice_draft(roles=["verb", "noun", "adjective", "adverb"], meanings=1)])
    assert st.needs_role() and not st.needs_meaning()


def test_choice_one_role_and_six_meanings_asks_only_the_meaning():
    st = b.ChoiceState([choice_draft(roles=["verb"], meanings=6)])
    assert not st.needs_role() and st.needs_meaning()


# Review Focus 3
def test_choice_a_phrase_is_never_asked_for_a_role():
    st = b.ChoiceState([choice_draft(roles=["phrase"], meanings=3, word="get along")])
    assert not st.needs_role() and st.needs_meaning()


# Review Focus 4
def test_choice_run_shows_three_buttons_and_one_shared_transcription():
    d = choice_draft(roles=["verb", "noun", "adjective"], shared_ipa="rʌn")
    assert b.ChoiceState([d]).role_labels() == ["verb  rʌn", "noun  rʌn", "adjective  rʌn"]


def test_choice_role_label_marks_a_lemma_role():
    assert b.role_label(Role("noun", "taɪə", lemma="tire")) == "noun  taɪə  (от tire)"


def test_choice_role_label_without_any_transcription():
    assert b.role_label(Role("verb")) == "verb"


def test_choice_role_own_transcription_wins_over_the_shared_one():
    assert b.role_label(Role("noun", "ˈrekɔːd"), "rɪˈkɔːd") == "noun  ˈrekɔːd"


def test_choice_choosing_a_role_redraws_the_meanings_with_its_definition():
    d = choice_draft(roles=["noun", "verb"], definitions=["a thing", "to write"], meanings=1)
    st = b.ChoiceState([d])
    before = st.meaning_labels()
    st.choose_role(1)
    assert st.current is d                      # курсор не двинулся
    assert st.meaning_labels() != before and "to write" in st.meaning_labels()[0]


def test_choice_meaning_labels_are_exactly_what_lands_on_the_card():
    d = choice_draft(roles=["verb"], definitions=["to write"], meanings=2)
    labels = b.meaning_labels(d)
    b.ChoiceState([d]).choose_meaning(1)
    assert d.values["meaning"] == labels[1]


def test_choice_choosing_a_meaning_moves_to_the_next_word():
    st = b.ChoiceState([choice_draft(meanings=2), choice_draft(meanings=2)])
    st.choose_meaning(0)
    assert st.counter == "2 из 2"


def test_choice_words_needing_no_choice_are_skipped_but_resolved():
    st = b.ChoiceState([choice_draft(roles=["verb"], meanings=1), choice_draft(meanings=2)])
    assert st.counter == "2 из 2"               # первое слово проехало само
    assert st.drafts[0].values["pos"] == "verb"


def test_choice_accept_all_takes_the_first_variant_everywhere():
    st = b.ChoiceState([choice_draft(roles=["noun", "verb"], meanings=3) for _ in range(5)])
    st.accept_all()
    assert st.done
    assert all(d.values["pos"] == "noun" for d in st.drafts)
    assert all(d.values["meaning"] for d in st.drafts)


def test_choice_accept_all_keeps_a_role_already_clicked():
    st = b.ChoiceState([choice_draft(roles=["noun", "verb"], meanings=3)])
    st.choose_role(1)
    st.accept_all()
    assert st.drafts[0].values["pos"] == "verb"


def test_choice_a_draft_with_no_variants_at_all_is_resolved_and_not_asked():
    st = b.ChoiceState([choice_draft(roles=[], meanings=0)])
    assert st.done and "pos" in st.drafts[0].missing


def test_choice_roles_without_a_single_meaning_can_still_be_confirmed():
    """Словарь дал роли, Reverso умер: окно обязано пускать дальше."""
    st = b.ChoiceState([choice_draft(roles=["noun", "verb"], meanings=0)])
    assert st.needs_role() and not st.needs_meaning()
    st.choose_role(1)
    st.choose_meaning(0)
    assert st.done and st.drafts[0].values["pos"] == "verb"
    assert "meaning" in st.drafts[0].missing


def test_choice_out_of_range_clicks_change_nothing():
    st = b.ChoiceState([choice_draft(roles=["noun", "verb"], meanings=2)])
    st.choose_role(9)
    st.choose_meaning(-1)
    assert st.current is not None and st.drafts[0].role_index == 0


def test_choice_empty_state_is_done_at_once():
    st = b.ChoiceState([])
    assert st.done and st.current is None and st.role_labels() == [] and st.meaning_labels() == []
    st.choose_role(0)
    st.choose_meaning(0)
    st.accept_all()
    assert st.done


# ------------------------------------------------------- parallel build phase

def bpick(word):
    return b.Pick(word, occ())


def ok_build(word, o):
    return draft(word)


def test_parallel_results_keep_the_order_of_the_picks():
    def slow_a(word, o):
        if word == "a":
            time.sleep(0.05)
        return draft(word)

    out = b.build_drafts([bpick("a"), bpick("b"), bpick("c")], slow_a, workers=3)
    assert [p.word for p, _, _ in out] == ["a", "b", "c"]
    assert all(d is not None for _, d, _ in out)


def test_parallel_words_are_built_at_the_same_time():
    lock = threading.Lock()
    state = {"now": 0, "max": 0}

    def build(word, o):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1
        return draft(word)

    b.build_drafts([bpick(str(i)) for i in range(6)], build, workers=3)
    assert state["max"] > 1


def test_parallel_one_word_blowing_up_does_not_touch_the_others():
    def build(word, o):
        if word == "boom":
            raise RuntimeError("boom")
        return draft(word)

    out = b.build_drafts([bpick("a"), bpick("boom"), bpick("c")], build, workers=3)
    assert [bool(d) for _, d, _ in out] == [True, False, True]
    assert [p.word for p, d, _ in out if d is None] == ["boom"]
    assert "boom" in out[1][2]


# Review Focus 2
def test_parallel_should_stop_leaves_the_rest_unbuilt_and_keeps_what_was_done():
    seen = {"n": 0}

    def stop():
        seen["n"] += 1
        return seen["n"] > 2

    out = b.build_drafts([bpick(str(i)) for i in range(10)], ok_build, workers=1,
                         should_stop=stop)
    assert len(out) == 10
    assert sum(1 for _, d, _ in out if d is not None) == 2
    assert all(e for _, d, e in out if d is None)          # у каждого — честная причина


def test_parallel_progress_is_reported_once_per_word():
    calls = []
    lock = threading.Lock()

    def progress(i, n, w):
        with lock:
            calls.append((i, n))

    b.build_drafts([bpick(str(i)) for i in range(5)], ok_build, progress=progress, workers=3)
    assert len(calls) == 5 and {n for _, n in calls} == {5}
    assert sorted(i for i, _ in calls) == [0, 1, 2, 3, 4]


def test_parallel_empty_picks_need_no_pool():
    assert b.build_drafts([], ok_build, workers=4) == []


def test_parallel_workers_are_clamped_to_at_least_one():
    out = b.build_drafts([bpick("a")], ok_build, workers=0)
    assert [p.word for p, _, _ in out] == ["a"]


# ------------------------------------------------------- choose phase in a batch

def test_run_batch_calls_choose_between_building_and_adding():
    order = []
    picks = [b.Pick("a", occ())]
    res = b.BatchResult()
    seen = []

    def choose(built, finish):
        order.append("choose")
        finish()

    b.run_batch(picks, lambda w: None, ok_build, lambda d: order.append("add"),
                res, sync_bg, seen.append, choose=choose)
    assert order == ["choose", "add"]
    assert seen == [res] and status(res) == {"a": b.CREATED}


def test_run_batch_without_choose_adds_everything_as_before():
    order = []
    res = b.BatchResult()
    seen = []
    b.run_batch([b.Pick("a", occ())], lambda w: None, ok_build,
                lambda d: order.append("add"), res, sync_bg, seen.append)
    assert order == ["add"] and seen == [res]


def test_run_batch_does_not_finish_until_choose_calls_finish():
    res = b.BatchResult()
    seen = []
    held = {}
    b.run_batch([b.Pick("a", occ())], lambda w: None, ok_build, lambda d: None,
                res, sync_bg, seen.append, choose=lambda built, finish: held.update(f=finish))
    assert seen == []                     # отчёт ещё не показан: пользователь выбирает
    held["f"]()
    assert seen == [res]


def test_run_batch_passes_workers_and_should_stop_to_the_build():
    got = {}

    def run_bg(work, ok, fail):
        ok(work())

    def spy(picks, build, progress=None, workers=6, should_stop=None):
        got.update(workers=workers, should_stop=should_stop)
        return []

    import anki_sentence_cards.batch as mod
    real, mod.build_drafts = mod.build_drafts, spy
    try:
        stop = lambda: False
        mod.run_batch([b.Pick("a", occ())], lambda w: None, ok_build, lambda d: None,
                      b.BatchResult(), run_bg, lambda r: None, workers=3, should_stop=stop)
    finally:
        mod.build_drafts = real
    assert got == {"workers": 3, "should_stop": stop}


def test_choice_a_single_role_from_a_base_form_is_always_shown():
    """Одна роль, и та от другого слова: пользователь обязан это увидеть."""
    d = choice_draft(roles=["noun"], meanings=1, word="tired")
    d.roles[0].lemma = "tire"
    assert b.needs_choice(d) is True
    st = b.ChoiceState([d])
    assert st.needs_role() and st.role_labels() == ["noun  (от tire)"]


def test_choice_a_single_role_of_the_word_itself_is_not_shown():
    assert b.needs_choice(choice_draft(roles=["noun"], meanings=1)) is False


def test_report_plain_carries_warnings_skipped_and_every_group():
    out = [b.Outcome("a", b.CREATED), b.Outcome("c", b.FAILED, ["перерыв прерван"])]
    text = b.report_plain(out, ["Партия остановлена: нет типа"], ["b"])
    assert "Партия остановлена: нет типа" in text
    assert "Пропущено вами: b" in text
    assert "Создано (1)" in text and "a" in text
    assert "Не создано (1)" in text and "c — перерыв прерван" in text


def test_report_plain_says_so_when_nothing_was_created():
    assert b.report_plain([], [], []) == "Ничего не создано."
