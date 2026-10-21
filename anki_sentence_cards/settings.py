import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Combo item meaning 'leave this note field empty'.
NOT_FILLED = ""


@dataclass
class Settings:
    books: list = field(default_factory=list)
    active_book: str = ""
    deck: str = ""
    notetype: str = ""
    field_map: dict = field(default_factory=dict)  # logical key -> note field name
    deepl_key: str = ""
    tts_lang: str = "en-GB"
    occurrence_limit: int = 50


def load_settings(raw: dict) -> Settings:
    d = Settings()
    return Settings(
        books=list(raw.get("books", d.books)),
        active_book=raw.get("active_book", d.active_book),
        deck=raw.get("deck", d.deck),
        notetype=raw.get("notetype", d.notetype),
        field_map=dict(raw.get("field_map", d.field_map)),
        deepl_key=raw.get("deepl_key", d.deepl_key),
        tts_lang=raw.get("tts_lang", d.tts_lang),
        occurrence_limit=int(raw.get("occurrence_limit", d.occurrence_limit)),
    )


def to_dict(s: Settings) -> dict:
    return {
        "books": list(s.books),
        "active_book": s.active_book,
        "deck": s.deck,
        "notetype": s.notetype,
        "field_map": dict(s.field_map),
        "deepl_key": s.deepl_key,
        "tts_lang": s.tts_lang,
        "occurrence_limit": s.occurrence_limit,
    }


def merge_for_save(raw: dict, s: Settings) -> dict:
    """Config to write back: keys unknown to the schema (hand edits) survive."""
    out = dict(raw)
    out.update(to_dict(s))
    return out


def add_book(books: List[str], path: str) -> List[str]:
    """Return books plus the normalized path (no empty, no duplicates)."""
    path = path.strip()
    if not path:
        return list(books)
    norm = os.path.normpath(path)
    return list(books) if norm in books else list(books) + [norm]


def remove_book(books: List[str], active: str, path: str) -> Tuple[List[str], str]:
    """Remove path; if it was active, the first remaining book becomes active."""
    rest = [b for b in books if b != path]
    if active == path or active not in rest:
        active = rest[0] if rest else ""
    return rest, active


def build_field_map(choices: Dict[str, str]) -> Tuple[Dict[str, str], bool]:
    """Drop 'not filled' entries; second value is False when front is missing.

    Only front is mandatory (ruling N7); other keys may stay empty.
    """
    result = {k: v for k, v in choices.items() if v != NOT_FILLED}
    return result, "front" in result
