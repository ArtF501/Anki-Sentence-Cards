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


class NoteError(Exception):
    """Could not write the note; the message is user-facing (Russian)."""


class NoteTypeMissing(NoteError):
    """Note type does not exist: the cause is shared by the whole batch.

    Means 'stop the batch', not 'mark this word as failed'.
    """


def check_front(draft: "CardDraft", field_map: Dict[str, str]) -> None:
    """Refuse a note whose front side would be empty or unmapped."""
    if not field_map.get("front"):
        raise NoteError("Поле лицевой стороны (Front) не сопоставлено")
    if not (draft.values.get("front") or "").strip():
        raise NoteError("Пустая лицевая сторона карточки (Front)")


def escape_search(text: str) -> str:
    """Escape text for use inside a quoted Anki search term."""
    out = text.replace("\\", "\\\\")
    for ch in ('"', "*", "_", ":"):
        out = out.replace(ch, "\\" + ch)
    return out


def sync_sound_name(values: Dict[str, str], old: str, new: str) -> None:
    """Point values['sound'] at the media name Anki actually used."""
    if new and new != old and "sound" in values:
        values["sound"] = values["sound"].replace(old, new)


def add_note(col, draft: "CardDraft", deck: str, notetype: str, field_map: Dict[str, str]) -> int:
    """Add the draft as a note and return its id. Audio is written first.

    Raises NoteError (Russian message) for: unknown note type, a field_map
    entry naming a field the note type no longer has, and Anki refusing the
    note (e.g. 'front' unmapped or empty). Caller contract (task 11): before
    the batch, check resolve_field_map's `unresolved` and that the note type
    exists, once; inside the per-word loop catch NoteError and, as a safety
    net, Exception. NoteTypeMissing (a NoteError subclass) means stop the
    whole batch, not mark one word. An empty or unmapped front is refused
    with NoteError before Anki is touched.
    """
    check_front(draft, field_map)
    model = col.models.by_name(notetype)
    if model is None:
        raise NoteTypeMissing("Тип заметки не найден: %s" % notetype)
    deck_id = col.decks.id(deck)
    if draft.audio and draft.audio_name:
        written = col.media.write_data(draft.audio_name, draft.audio)
        if isinstance(written, str):
            sync_sound_name(draft.values, draft.audio_name, written)
            draft.audio_name = written
    note = col.new_note(model)
    for key, value in draft.values.items():
        name = field_map.get(key)
        if name:
            try:
                note[name] = value
            except KeyError:
                raise NoteError("В типе заметки нет поля «%s»" % name)
    for tag in note_tags(draft.missing):
        note.add_tag(tag)
    try:
        col.add_note(note, deck_id)
    except Exception as e:
        raise NoteError("Anki не принял заметку: %s" % e)
    return note.id


def find_duplicate(col, deck: str, word: str) -> Optional[int]:
    """Id of a note in the deck whose first field contains the word, else None.

    One Anki search prefilters candidates; only they are checked by regex.
    A failing search raises NoteError: it must not look like 'no duplicate'.
    Task 11 should catch it, tell the user duplicate detection is off, and
    decide whether to continue; it is not the same as returning None.
    """
    query = 'deck:"%s" "%s"' % (escape_search(deck), escape_search(word))
    pattern = re.compile(r"\b%s\b" % re.escape(word), re.IGNORECASE)
    try:
        ids = col.find_notes(query)
    except Exception as e:
        raise NoteError("Не удалось проверить дубликаты: %s" % e)
    for nid in ids:
        first = col.get_note(nid).fields[0]
        if pattern.search(re.sub(r"<[^>]+>", "", first)):
            return nid
    return None
