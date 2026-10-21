"""Sentence translation: DeepL first, public Google endpoint as fallback."""
from __future__ import annotations

from dataclasses import dataclass

from . import http
from .http import SourceError

DEEPL_URL = "https://api-free.deepl.com/v2/translate"
GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"


@dataclass
class Translation:
    text: str
    engine: str


def parse_deepl(payload) -> str:
    try:
        text = payload["translations"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise SourceError("DeepL вернул непонятный ответ")
    if not isinstance(text, str) or not text.strip():
        raise SourceError("DeepL вернул пустой перевод")
    return text


def parse_google(payload) -> str:
    try:
        text = "".join(part[0] for part in payload[0] if part and part[0])
    except (KeyError, IndexError, TypeError):
        raise SourceError("Google Translate вернул непонятный ответ")
    if not text.strip():
        raise SourceError("Google Translate вернул пустой перевод")
    return text


def _deepl(text: str, key: str, target: str) -> str:
    payload = http.post_form(
        DEEPL_URL,
        {"text": text, "target_lang": target.upper()},
        headers={"Authorization": "DeepL-Auth-Key " + key},
    )
    return parse_deepl(payload)


def _google(text: str, target: str) -> str:
    payload = http.get_json(
        GOOGLE_URL,
        {"client": "gtx", "sl": "auto", "tl": target.lower(), "dt": "t", "q": text},
    )
    return parse_google(payload)


def translate(text: str, deepl_key: str, target: str = "RU") -> Translation:
    if deepl_key and deepl_key.strip():
        try:
            return Translation(_deepl(text, deepl_key.strip(), target), "deepl")
        except SourceError:
            pass  # fall through to Google
    try:
        return Translation(_google(text, target), "google")
    except SourceError as e:
        raise SourceError("перевод недоступен: %s" % e)
