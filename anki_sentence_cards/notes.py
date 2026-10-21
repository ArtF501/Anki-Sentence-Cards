"""Write a CardDraft into the Anki collection.

No module-level anki/aqt imports: the collection is passed in and used by duck
typing, so the pure part (resolve_field_map) is testable without Anki.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .card import CardDraft

DEFAULT_FIELD_NAMES = {
    "front": "Front",
    "translate": "Translate",
    "pos": "Type of word",
    "ipa": "Transcription of word",
    "meaning": "Meaning",
    "sound": "Sound of word",
}

# Never filled by the addon, never offered for mapping.
_EXCLUDED = ("Sound of sentence", "Notes")

TAG_ALL = "asc"
TAG_INCOMPLETE = "auto-incomplete"


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()


def resolve_field_map(notetype_fields: List[str], saved: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """Map logical keys to note field names; return (map, unresolved keys)."""
    excluded = {_norm(n) for n in _EXCLUDED}
    fields = [f for f in notetype_fields if _norm(f) not in excluded]
    result: Dict[str, str] = {}
    unresolved: List[str] = []
    for key, default in DEFAULT_FIELD_NAMES.items():
        found = None
        for cand in (saved.get(key), default):
            if cand and cand in fields:
                found = cand
                break
        if found is None:
            for cand in (saved.get(key), default):
                if cand:
                    found = next((f for f in fields if _norm(f) == _norm(cand)), None)
                    if found:
                        break
        if found is None:
            unresolved.append(key)
        else:
            result[key] = found
    return result, unresolved


def note_tags(missing: List[str]) -> List[str]:
    return [TAG_ALL] + ([TAG_INCOMPLETE] if missing else [])


def add_note(col, draft: "CardDraft", deck: str, notetype: str, field_map: Dict[str, str]) -> int:
    """Add the draft as a note and return its id. Audio is written first."""
    model = col.models.by_name(notetype)
    if model is None:
        raise ValueError("Note type not found: %s" % notetype)
    deck_id = col.decks.id(deck)
    if draft.audio and draft.audio_name:
        col.media.write_data(draft.audio_name, draft.audio)
    note = col.new_note(model)
    for key, value in draft.values.items():
        name = field_map.get(key)
        if name:
            note[name] = value
    for tag in note_tags(draft.missing):
        note.add_tag(tag)
    col.add_note(note, deck_id)
    return note.id


def find_duplicate(col, deck: str, word: str) -> Optional[int]:
    """Id of a note in the deck whose first field contains the word, else None."""
    query = 'deck:"%s" "%s"' % (deck.replace('"', '\\"'), word.replace('"', '\\"'))
    pattern = re.compile(r"\b%s\b" % re.escape(word), re.IGNORECASE)
    for nid in col.find_notes(query):
        first = col.get_note(nid).fields[0]
        if pattern.search(re.sub(r"<[^>]+>", "", first)):
            return nid
    return None
