from types import SimpleNamespace

from anki_sentence_cards import batch as b
from anki_sentence_cards.book.search import Occurrence, find_occurrences, mark_match
from anki_sentence_cards.card import CardDraft
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
