import pytest

from anki_sentence_cards.sources import http, tts


@pytest.fixture
def net(monkeypatch):
    state = {"resp": b"ID3data", "calls": []}

    def get_bytes(url, params=None, timeout=10.0):
        state["calls"].append((url, params))
        if isinstance(state["resp"], Exception):
            raise state["resp"]
        return state["resp"]

    monkeypatch.setattr(http, "get_bytes", get_bytes)
    return state


def test_request_params(net):
    assert tts.synthesize("run") == b"ID3data"
    url, params = net["calls"][0]
    assert url == "https://translate.google.com/translate_tts"
    assert params == {"client": "tw-ob", "tl": "en-GB", "q": "run"}


def test_lang_is_passed_to_request(net):
    tts.synthesize("run", "en-US")
    assert net["calls"][0][1]["tl"] == "en-US"


def test_empty_response_raises_source_error(net):
    net["resp"] = b""
    with pytest.raises(http.SourceError):
        tts.synthesize("run")


def test_http_error_passes_through(net):
    net["resp"] = http.SourceError("нет соединения с сервисом")
    with pytest.raises(http.SourceError):
        tts.synthesize("run")


def test_media_name_is_stable_and_collision_free():
    assert tts.media_name("run", b"a") == tts.media_name("run", b"a")
    assert tts.media_name("run", b"a") != tts.media_name("run", b"b")
    assert tts.media_name("run", b"a").endswith(".mp3")


def test_media_name_strips_unsafe_characters():
    name = tts.media_name("give up", b"a")
    assert name.startswith("give_up_") and "/" not in name and " " not in name
    for bad in ("../x", "a\\b:c*?", "", "   "):
        n = tts.media_name(bad, b"a")
        assert not set(n) & set('/\\:*?"<>| []') and "." not in n.replace(".mp3", "")


def test_empty_word_makes_no_request(net):
    for w in ("", "   ", "\t\n"):
        with pytest.raises(http.SourceError):
            tts.synthesize(w)
    assert net["calls"] == []


def test_media_name_long_word_is_truncated():
    name = tts.media_name("x" * 300, b"a")
    assert len(name) <= 80 and name.endswith(".mp3")
    name = tts.media_name("a" * 59 + " " + "b" * 300, b"a")
    assert "__" not in name and not name.startswith("_")


def test_media_name_unicode_word():
    assert tts.media_name("Café", b"a").startswith("café_")
    assert tts.media_name("привет", b"a").startswith("привет_")


def test_media_name_fallback_word():
    for w in ("...", "!!!", "..", "[]", "-_-"):
        assert tts.media_name(w, b"a").startswith("word_")
    assert tts.media_name("...", b"a") == tts.media_name("!!!", b"a")
    assert tts.media_name("...", b"a").startswith("word_")
    assert tts.media_name("[sound:x]", b"a").startswith("sound_x_")
