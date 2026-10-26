"""Loading a book into sentences, with an on-disk JSON cache."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .loaders import load_text
from .normalize import normalize
from .sentences import split_sentences


_CACHE_VERSION = 1  # bump when normalize/split rules change


@dataclass
class Book:
    path: str
    sentences: List[str]


def _cache_file(path: Path, cache_dir: Path) -> Path:
    key = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
    return cache_dir / (key + ".json")


def load_book(path: Path, cache_dir: Path) -> Book:
    path = Path(path).resolve()
    cache_dir = Path(cache_dir)
    mtime = path.stat().st_mtime
    cache = _cache_file(path, cache_dir)
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        sents = data["sentences"]
        if (
            data["v"] == _CACHE_VERSION
            and data["mtime"] == mtime
            and isinstance(sents, list)
            and all(isinstance(x, str) for x in sents)
        ):
            return Book(str(path), sents)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    sentences = split_sentences(normalize(load_text(path)))
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps({"v": _CACHE_VERSION, "mtime": mtime, "sentences": sentences}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass
    return Book(str(path), sentences)
