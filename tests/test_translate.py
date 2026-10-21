import pytest

from anki_sentence_cards.sources import http, translate

# Recorded-shape responses.
DEEPL_OK = {"translations": [{"detected_source_language": "EN", "text": "Привет"}]}
GOOGLE_OK = [[["Привет, ", "Hello, ", None, None, 10], ["мир", "world", None, None, 10]], None, "en"]


@pytest.fixture
def net(monkeypatch):
    state = {"deepl": DEEPL_OK, "google": GOOGLE_OK, "posts": [], "gets": []}

    def post_form(url, data, timeout=10.0, headers=None):
        state["posts"].append((url, data, headers))
        if isinstance(state["deepl"], Exception):
            raise state["deepl"]
        return state["deepl"]

    def get_json(url, params=None, timeout=10.0):
        state["gets"].append((url, params))
        if isinstance(state["google"], Exception):
            raise state["google"]
        return state["google"]

    monkeypatch.setattr(http, "post_form", post_form)
    monkeypatch.setattr(http, "get_json", get_json)
    return state


def test_deepl_used_when_key_present(net):
    t = translate.translate("Hello", deepl_key="k")
    assert t == translate.Translation("Привет", "deepl")
    url, data, headers = net["posts"][0]
    assert url == "https://api-free.deepl.com/v2/translate"
    assert headers["Authorization"] == "DeepL-Auth-Key k"
    assert data["target_lang"] == "RU" and data["text"] == "Hello"
    assert net["gets"] == []


def test_falls_back_to_google_when_key_empty(net):
    t = translate.translate("Hello", deepl_key="")
    assert t.engine == "google"
    assert t.text == "Привет, мир"
    assert net["posts"] == []
    assert net["gets"][0][1]["tl"] == "ru"


def test_falls_back_to_google_when_deepl_errors(net):
    net["deepl"] = http.SourceError("down")
    assert translate.translate("Hello", deepl_key="k").engine == "google"


def test_falls_back_when_deepl_response_malformed(net):
    net["deepl"] = {"translations": []}
    assert translate.translate("Hello", deepl_key="k").engine == "google"


def test_both_dead_raises_source_error(net):
    net["deepl"] = http.SourceError("a")
    net["google"] = http.SourceError("b")
    with pytest.raises(http.SourceError):
        translate.translate("Hello", deepl_key="k")


def test_google_malformed_raises_source_error(net):
    net["google"] = {"unexpected": 1}
    with pytest.raises(http.SourceError):
        translate.translate("Hello", deepl_key="")


def test_parsers_on_recorded_samples():
    assert translate.parse_deepl(DEEPL_OK) == "Привет"
    assert translate.parse_google(GOOGLE_OK) == "Привет, мир"


@pytest.mark.parametrize("bad", [["x"], [["ab", "cd"]], "Hello", [[[1, "a"]]], [[[]]], [[]]])
def test_parse_google_rejects_wrong_shapes(bad):
    with pytest.raises(http.SourceError):
        translate.parse_google(bad)


def test_whitespace_only_key_goes_to_google(net):
    assert translate.translate("Hello", deepl_key="  ").engine == "google"
    assert net["posts"] == []
