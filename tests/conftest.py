import pytest

from anki_sentence_cards.sources import http


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Safety net: any test that reaches the real transport fails loudly.
    Tests that need a transport override http._urlopen themselves."""

    def blocked(req, timeout):
        raise AssertionError("network in test")

    monkeypatch.setattr(http, "_urlopen", blocked)
