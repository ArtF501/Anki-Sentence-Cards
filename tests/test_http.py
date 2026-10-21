import io
import socket
import urllib.error

import pytest

from anki_sentence_cards.sources import http


class FakeResp:
    def __init__(self, body=b"{}"):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def transport(monkeypatch):
    """Replaces the one function that touches the network; records calls."""
    state = {"calls": [], "script": [], "sleeps": []}

    def fake_open(req, timeout):
        state["calls"].append((req, timeout))
        item = state["script"].pop(0) if len(state["script"]) > 1 else state["script"][0]
        if isinstance(item, BaseException):
            raise item
        return FakeResp(item)

    monkeypatch.setattr(http, "_urlopen", fake_open)
    monkeypatch.setattr(http, "_sleep", lambda s: state["sleeps"].append(s))
    return state


def _http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b""))


def test_get_json_ok_and_params_encoded(transport):
    transport["script"] = [b'{"a": 1}']
    assert http.get_json("http://x/y", {"q": "a b"}) == {"a": 1}
    req, timeout = transport["calls"][0]
    assert req.full_url == "http://x/y?q=a+b"
    assert timeout <= 10


def test_post_form_sends_body_and_headers(transport):
    transport["script"] = [b"[]"]
    http.post_form("http://x", {"t": "hi"}, headers={"Authorization": "K"})
    req, _ = transport["calls"][0]
    assert req.data == b"t=hi"
    assert req.get_header("Authorization") == "K"


def test_get_bytes(transport):
    transport["script"] = [b"\x00\x01"]
    assert http.get_bytes("http://x") == b"\x00\x01"


def test_timeout_raises_source_error(transport):
    transport["script"] = [socket.timeout("timed out")]
    with pytest.raises(http.SourceError):
        http.get_json("http://x")


def test_retries_twice_then_raises(transport):
    transport["script"] = [urllib.error.URLError("down")]
    with pytest.raises(http.SourceError):
        http.get_json("http://x")
    assert len(transport["calls"]) == 3
    assert len(transport["sleeps"]) == 2


def test_recovers_on_second_attempt(transport):
    transport["script"] = [socket.timeout(), b'{"ok": true}']
    assert http.get_json("http://x") == {"ok": True}
    assert len(transport["calls"]) == 2


def test_http_500_raises_source_error(transport):
    transport["script"] = [_http_error(500)]
    with pytest.raises(http.SourceError) as e:
        http.get_json("http://x")
    assert "500" in str(e.value)
    assert len(transport["calls"]) == 3


def test_http_4xx_not_retried(transport):
    transport["script"] = [_http_error(403)]
    with pytest.raises(http.SourceError):
        http.get_json("http://x")
    assert len(transport["calls"]) == 1


def test_bad_json_raises_source_error(transport):
    transport["script"] = [b"<html>oops</html>"]
    with pytest.raises(http.SourceError):
        http.get_json("http://x")


def test_timeout_is_capped_at_10(transport):
    transport["script"] = [b"{}"]
    http.get_json("http://x", timeout=999)
    assert transport["calls"][0][1] == 10


def test_error_text_has_no_url_or_traceback(transport):
    transport["script"] = [urllib.error.URLError("boom")]
    with pytest.raises(http.SourceError) as e:
        http.get_json("http://secret.example/path?key=SECRET")
    assert "SECRET" not in str(e.value)
    assert "Traceback" not in str(e.value)


def test_bad_url_raises_source_error(transport):
    transport["script"] = [ValueError("unknown url type")]
    with pytest.raises(http.SourceError):
        http.get_json("nonsense")


def test_http_error_is_closed(transport):
    closed = []
    err = _http_error(403)
    err.close = lambda: closed.append(1)
    transport["script"] = [err]
    with pytest.raises(http.SourceError):
        http.get_json("http://x")
    assert closed


def test_real_network_is_blocked_by_default():
    with pytest.raises(AssertionError, match="network in test"):
        http._urlopen(None, 1)
