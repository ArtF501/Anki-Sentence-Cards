"""Every role of a word, gathered from whatever source is alive right now.

The primary dictionary goes down word by word, so a word is asked of several
sources and the answer is assembled field by field: the roles come from the
first source that answered, a transcription may come from the next one, and a
base form is always asked as well — but its roles arrive labelled, never
pretending to be the word's own.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, List, Optional, Sequence

from ..book.search import base_form_candidates
from . import dictionary, wiktionary
from .http import SourceError
from .roles import Role, WordData, merge_roles, order_roles

Lookup = Callable[[str], WordData]


def _answered(data) -> bool:
    return data is not None and bool(getattr(data, "roles", None))


def _has_ipa(roles: List[Role], shared: str) -> bool:
    return bool(shared) or any(r.ipa for r in roles)


def _fill_ipa(roles: List[Role], donor: WordData) -> None:
    """Take from a later source only what the first one left empty."""
    by_pos = {}
    for role in donor.roles:
        if role.ipa and role.pos not in by_pos:
            by_pos[role.pos] = role.ipa
    for role in roles:
        if not role.ipa and role.pos in by_pos:
            role.ipa = by_pos[role.pos]


def _fill_from_lemma(roles: List[Role]) -> None:
    """A role with no transcription takes the base form's — same part of speech only.

    `supervised` keeps the transcription of `supervise` (the spec accepts the
    missing final -d as the lesser evil), while `tired` never takes /taɪə/ from
    `tire`: that is a noun and `tired` is an adjective, so they never match.
    """
    donors = {}
    for role in roles:
        if role.lemma and role.ipa and role.pos not in donors:
            donors[role.pos] = role.ipa
    for role in roles:
        if not role.lemma and not role.ipa and role.pos in donors:
            role.ipa = donors[role.pos]


def collect_roles(word: str,
                  lookups: Sequence[Lookup],
                  ipa_lookup: Optional[Callable[[str], str]] = None,
                  candidates: Sequence[str] = ()) -> WordData:
    """Roles of the word plus those of one base form, labelled and last.

    Raises SourceError only when nothing answered about anything: an empty
    field with an honest reason is fine, an invented part of speech is not.
    """
    reason = ""
    roles: List[Role] = []
    shared = ""
    for lookup in lookups:
        try:
            data = lookup(word)
        except SourceError as e:
            reason = reason or str(e)
            continue
        if not _answered(data):
            reason = reason or "источник ничего не вернул"
            continue
        if not roles:
            roles = [replace(r) for r in data.roles]
            shared = data.shared_ipa
        else:
            _fill_ipa(roles, data)
            shared = shared or data.shared_ipa
        if _has_ipa(roles, shared):
            break

    lemma_roles: List[Role] = []
    accepted = ""
    for candidate in candidates:
        for lookup in lookups:
            try:
                data = lookup(candidate)
            except SourceError as e:
                reason = reason or str(e)
                continue
            if not _answered(data):
                continue
            # the base form's own transcription stays on the labelled roles:
            # tire's /taɪə/ is not the transcription of tired.
            lemma_roles = [replace(r, lemma=candidate,
                                   ipa=r.ipa or data.shared_ipa) for r in data.roles]
            accepted = candidate
            break
        if accepted:
            break

    out = order_roles(merge_roles(roles + lemma_roles))
    _fill_from_lemma(out)
    if not out:
        raise SourceError(reason or "ни один словарь не ответил")

    if ipa_lookup is not None and not _has_ipa(out, shared):
        try:
            shared = (ipa_lookup(word) or "").strip()
        except SourceError:
            shared = ""
        if not shared and accepted:
            try:
                found = (ipa_lookup(accepted) or "").strip()
            except SourceError:
                found = ""
            if found:
                for role in out:
                    if role.lemma == accepted and not role.ipa:
                        role.ipa = found
    return WordData(out, shared)


def fetch_word_data(word: str, settings) -> WordData:
    """The live wiring: real sources, real base forms. No logic of its own.

    A phrase gets no base-form candidates: the first word of `get along` is a
    word in its own right, and its roles are not the phrase's.
    """
    single = len((word or "").split()) == 1
    return collect_roles(
        word,
        [dictionary.lookup, wiktionary.lookup],
        wiktionary.lookup_ipa if settings.wiktionary_ipa else None,
        base_form_candidates(word) if single else (),
    )
