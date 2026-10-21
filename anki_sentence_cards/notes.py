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


def mappable_fields(notetype_fields: List[str]) -> List[str]:
    """Note type fields the addon may fill (without the excluded ones)."""
    excluded = {_norm(n) for n in _EXCLUDED}
    return [f for f in notetype_fields if _norm(f) not in excluded]


def resolve_field_map(notetype_fields: List[str], saved: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """Map logical keys to note field names; return (map, unresolved keys).

    Policy for the caller (task 11), checked once before the batch:
    only an unresolved 'front' is fatal (it lands in `unresolved` like any
    other key). Any other unresolved key means: warn the user once, leave
    that field empty, still create the card.
    """
    fields = mappable_fields(notetype_fields)
    result: Dict[str, str] = {}
    unresolved: List[str] = []
    for key, default in DEFAULT_FIELD_NAMES.items():
        if saved.get(key) == "" and key != "front":
            continue  # explicit 'do not fill': respected, not unresolved
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


def plan_field_map(fields: List[str], saved: Dict[str, str], map_notetype: str,
                   new_notetype: str) -> Tuple[Dict[str, str], List[str]]:
    """Map to keep and unresolved keys for new_notetype.

    A saved map built for another note type is dropped, never reused.
    """
    keep = dict(saved) if map_notetype == new_notetype else {}
    _, unresolved = resolve_field_map(fields, keep)
    return keep, unresolved


def note_tags(missing: List[str]) -> List[str]:
    return [TAG_ALL] + ([TAG_INCOMPLETE] if missing else [])


class NoteError(Exception):
    """Could not write the note; the message is user-facing (Russian)."""


class NoteTypeMissing(NoteError):
    """Note type does not exist: the cause is shared by the whole batch.

    Means 'stop the batch', not 'mark this word as failed'.
    """


def check_front(draft: "CardDraft", field_map: Dict[str, str]) -> None:
    """Refuse a note whose front side would be empty or unmapped.

    Markup without text ('<b></b>', '<br>', '&nbsp;') counts as empty.
    """
    if not field_map.get("front"):
        raise NoteError("Поле лицевой стороны (Front) не сопоставлено")
    text = re.sub(r"<[^>]*>", "", draft.values.get("front") or "")
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    if not text.strip():
        raise NoteError("Пустая лицевая сторона карточки (Front)")


class DuplicateCheckFailed(NoteError):
    """find_duplicate could not search. Means 'duplicate check is off', not
    'this word failed'; see find_duplicate for the rule."""


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

    Order of checks: check_front first, then the note type. So with an empty
    front AND a missing note type the caller gets NoteError, not
    NoteTypeMissing.

    Raises (messages are Russian, user-facing):
    - NoteError: empty or unmapped front (refused before Anki is touched),
      a field_map entry naming a field the note type no longer has, or Anki
      rejecting the note in add_note. Mark this word failed, go on.
    - NoteTypeMissing (subclass of NoteError): unknown note type. Stop the
      whole batch. Catch it before plain NoteError.
    Other Anki calls here (deck, media, new_note) are not wrapped and may
    raise raw exceptions, so the loop must also catch Exception as a safety
    net.

    Caller contract: before the batch, once, run resolve_field_map (see its
    policy) and verify the note type exists.
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
    Any failure raises DuplicateCheckFailed, never silently None.
    Caller rule (task 11): on DuplicateCheckFailed warn the user ONCE, turn
    duplicate checking off for the rest of the batch and continue. Do not
    stop the batch and do not mark the word failed: a duplicate is an
    inconvenience, not data corruption.
    """
    query = 'deck:"%s" "%s"' % (escape_search(deck), escape_search(word))
    pattern = re.compile(r"\b%s\b" % re.escape(word), re.IGNORECASE)
    try:
        for nid in col.find_notes(query):
            first = col.get_note(nid).fields[0]
            if pattern.search(re.sub(r"<[^>]+>", "", first)):
                return nid
    except Exception as e:
        raise DuplicateCheckFailed("Не удалось проверить дубликаты: %s" % e)
    return None
