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
        assert not set(n) & set('/\\:*?"<>| ') and not n.startswith(".")
