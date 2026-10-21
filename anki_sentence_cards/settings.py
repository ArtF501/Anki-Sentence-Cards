import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Combo item meaning 'leave this note field empty'.
NOT_FILLED = ""
TTS_LANGS = ("en-GB", "en-US")


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


def _str(v, default: str) -> str:
    return v if isinstance(v, str) else default


def load_settings(raw) -> Settings:
    """Build Settings from a possibly damaged config; bad values fall back."""
    d = Settings()
    if not isinstance(raw, dict):
        raw = {}
    books = raw.get("books")
    books = [b for b in books if isinstance(b, str) and b] if isinstance(books, list) else []
    fm = raw.get("field_map")
    fm = {k: v for k, v in fm.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(fm, dict) else {}
    lang = raw.get("tts_lang")
    try:
        limit = int(raw.get("occurrence_limit", d.occurrence_limit))
    except (TypeError, ValueError, OverflowError):
        limit = d.occurrence_limit
    if isinstance(raw.get("occurrence_limit"), bool) or limit < 1:
        limit = d.occurrence_limit
    return Settings(
        books=books,
        active_book=_str(raw.get("active_book"), d.active_book),
        deck=_str(raw.get("deck"), d.deck),
        notetype=_str(raw.get("notetype"), d.notetype),
        field_map=fm,
        deepl_key=_str(raw.get("deepl_key"), d.deepl_key),
        tts_lang=lang if lang in TTS_LANGS else d.tts_lang,
        occurrence_limit=limit,
    )


def normalize_active(books: List[str], active: str) -> str:
    """Active book must be one of books; otherwise the first (or empty)."""
    if active in books:
        return active
    return books[0] if books else ""


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
    """Keep 'not filled' as an explicit "" entry so it survives a reload.

    Second value is False when front is missing. Only front is mandatory
    (ruling N7); other keys may be disabled.
    """
    return dict(choices), bool(choices.get("front"))
