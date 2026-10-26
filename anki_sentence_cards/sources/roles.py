"""Shared vocabulary of the word sources: one role of a word, and all of them.

A "role" is one part of speech a word can be used in, with the transcription
and the English definition that belong to that use. Sources disagree and
repeat themselves, so every source returns a WordData and the merging rules
live here, in one place, with no network and no Anki.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List


@dataclass
class Role:
    pos: str                # "verb", lower case
    ipa: str = ""           # no slashes; "" when the source tied none to this role
    definition: str = ""    # the English definition of this role
    lemma: str = ""         # base form the role came from; "" = the word itself
    source: str = ""        # "dictionaryapi" | "wiktionary"


@dataclass
class WordData:
    roles: List[Role] = field(default_factory=list)
    shared_ipa: str = ""    # transcription the source tied to no role at all


_FILL = ("ipa", "definition", "source")


def merge_roles(roles: List[Role]) -> List[Role]:
    """Collapse repeats of the same (pos, lemma), filling empty fields from them.

    Order of first appearance is kept: the first definition wins, and a later
    repeat only contributes what the first one left empty.
    """
    out: List[Role] = []
    index = {}
    for role in roles:
        key = (role.pos, role.lemma)
        if key not in index:
            index[key] = len(out)
            out.append(replace(role))
            continue
        kept = out[index[key]]
        for name in _FILL:
            if not getattr(kept, name) and getattr(role, name):
                setattr(kept, name, getattr(role, name))
    return out


def order_roles(roles: List[Role]) -> List[Role]:
    """The word's own roles first, the base form's below; order kept within each."""
    return sorted(roles, key=lambda r: bool(r.lemma))
