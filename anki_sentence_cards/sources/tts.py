"""Word pronunciation mp3 from Google Translate TTS (stdlib only)."""
from __future__ import annotations

import hashlib
import re

from . import http
from .http import SourceError

URL = "https://translate.google.com/translate_tts"


def synthesize(word: str, lang: str = "en-GB") -> bytes:
    if not word or not word.strip():
        raise SourceError("нечего озвучивать: пустое слово")
    data = http.get_bytes(URL, {"client": "tw-ob", "tl": lang, "q": word})
    if not data:
        raise SourceError("сервис озвучки вернул пустой ответ")
    if data.lstrip()[:1] in (b"<", b"{"):
        raise SourceError("сервис озвучки вернул не звук (похоже на веб-страницу)")
    if not (data[:3] == b"ID3" or data[0] == 0xFF):
        raise SourceError("сервис озвучки вернул не mp3")
    return data


def media_name(word: str, data: bytes) -> str:
    safe = re.sub(r"[^\w-]+", "_", word.strip().lower())[:60].strip("_-") or "word"
    return "%s_%s.mp3" % (safe, hashlib.sha1(data).hexdigest()[:8])
