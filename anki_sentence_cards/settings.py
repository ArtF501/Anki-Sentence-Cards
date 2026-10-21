from dataclasses import dataclass, field


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
