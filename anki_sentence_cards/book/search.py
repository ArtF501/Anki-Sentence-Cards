"""Word and phrase search over a list of sentences, with simple inflection."""
import html
import re
from dataclasses import dataclass
from typing import List, Tuple

from .normalize import normalize_query

_IRREGULAR_DATA = """
be: am is are was were been being
arise: arose arisen
bear: bore born borne
beat: beaten
become: became
begin: began begun
bend: bent
bite: bit bitten
blow: blew blown
break: broke broken
bring: brought
build: built
burn: burnt
buy: bought
catch: caught
choose: chose chosen
come: came
cost:
cut:
deal: dealt
dig: dug
do: did done does
draw: drew drawn
dream: dreamt
drink: drank drunk
drive: drove driven
eat: ate eaten
fall: fell fallen
feed: fed
feel: felt
fight: fought
find: found
flee: fled
fly: flew flown
forget: forgot forgotten
forgive: forgave forgiven
freeze: froze frozen
get: got gotten
give: gave given
go: went gone goes
grow: grew grown
hang: hung
have: has had
hear: heard
hide: hid hidden
hit:
hold: held
hurt:
keep: kept
know: knew known
lay: laid
lead: led
leave: left
lend: lent
let:
lie: lay lain
light: lit
lose: lost
make: made
mean: meant
meet: met
pay: paid
put:
read:
ride: rode ridden
ring: rang rung
rise: rose risen
run: ran
say: said
see: saw seen
seek: sought
sell: sold
send: sent
set:
shake: shook shaken
shine: shone
shoot: shot
show: shown
shut:
sing: sang sung
sink: sank sunk
sit: sat
sleep: slept
slide: slid
speak: spoke spoken
spend: spent
spread:
stand: stood
steal: stole stolen
stick: stuck
strike: struck
swear: swore sworn
sweep: swept
swim: swam swum
swing: swung
take: took taken
teach: taught
tear: tore torn
tell: told
think: thought
throw: threw thrown
understand: understood
wake: woke woken
wear: wore worn
win: won
write: wrote written
"""
_IRREGULAR = {}
for _line in _IRREGULAR_DATA.strip().splitlines():
    _b, _f = _line.split(":")
    _IRREGULAR[_b.strip()] = _f.split()
_IRREGULAR_BACK = {}
for _b, _fs in _IRREGULAR.items():
    for _f in _fs:
        _IRREGULAR_BACK.setdefault(_f, []).append(_b)
# Words that look inflected but are words of their own: never cut back.
_NO_REVERSE = {
    "evening", "morning", "news", "during", "nothing", "something",
    "anything", "everything", "king", "thing", "wicked", "naked",
    "sacred", "hundred", "bed", "red", "this", "his", "was", "has",
}
# Real words that must never be produced as a bare stem of a longer word.
_NOISE_STEMS = {"us", "out", "her"}
_VOWELS = "aeiou"


def _single_forms(w: str) -> List[str]:
    forms = [w]
    forms += _IRREGULAR.get(w, [])
    for base in _IRREGULAR_BACK.get(w, []):
        forms.append(base)
        forms += _IRREGULAR[base]
    if w in _NO_REVERSE:
        return forms + [w + "s"]
    head = len(forms)
    if w.endswith("ing") and len(w) > 4:
        stem = w[:-3]
        forms += [stem, stem + "e"]
        if stem[-1] == stem[-2]:
            forms.append(stem[:-1])
    if w.endswith("ied") and len(w) > 3:
        forms += [w[:-3] + "y", w[:-1]]
    elif w.endswith("ed") and len(w) > 4:
        stem = w[:-2]
        forms += [stem, stem + "e"]
        if stem[-1] == stem[-2]:
            forms.append(stem[:-1])
    if w.endswith("ies") and len(w) > 4:
        forms.append(w[:-3] + "y")
    elif w.endswith("es") and len(w) > 4:
        forms.append(w[:-2])
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        forms.append(w[:-1])

    if len(w) > 1 and w[-1] == "y" and w[-2] not in _VOWELS:
        forms += [w[:-1] + "ies", w[:-1] + "ied", w + "ing"]
    elif w.endswith("e") and len(w) > 2:
        forms += [w + "s", w[:-1] + "ing"]
        if not (len(w) <= 3 and w.endswith("ee")):  # see -> seed is not a form
            forms.append(w + "d")
    else:
        forms += [w + "s", w + "ed", w + "ing"]
        if w.endswith(("s", "x", "z", "ch", "sh")):
            forms.append(w + "es")
        if w.endswith("o"):
            forms.append(w + "es")
        if (
            len(w) >= 3
            and w[-1] not in _VOWELS + "wxy"
            and w[-2] in _VOWELS
            and w[-3] not in _VOWELS
        ):
            forms += [w + w[-1] + "ed", w + w[-1] + "ing"]
    # a bare stem that is a word of its own (using -> us, hers -> her) is noise
    return forms[:head] + [
        f for f in forms[head:]
        if not (len(f) < len(w) and (len(f) < 3 or f in _NOISE_STEMS))
    ]


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def word_forms(query: str) -> List[str]:
    """Search variants for a word or phrase; the exact form comes first.

    For a phrase only the first word is inflected.
    """
    words = normalize_query(query).lower().split()
    if not words:
        return []
    rest = " ".join(words[1:])
    out = []
    for f in _dedupe(_single_forms(words[0])):
        out.append(f + " " + rest if rest else f)
    return out


MAX_BASE_FORMS = 3


def base_form_candidates(word: str) -> List[str]:
    """Shorter forms the word may have been inflected from, nearest first.

    Only a guess: `tired` yields `tire`, which is a different word. The caller
    labels what comes back and never silently treats it as the word itself.
    """
    words = normalize_query(word).lower().split()
    if not words:
        return []
    head = words[0]
    shorter = [
        f for f in _dedupe(_single_forms(head))
        if f != head and len(f) <= len(head) and len(f) >= 3
    ]
    shorter.sort(key=len, reverse=True)
    return shorter[:MAX_BASE_FORMS]


@dataclass
class Occurrence:
    sentence_index: int
    sentence: str
    matched_form: str
    start: int
    end: int
    exact: bool


def _build_regex(query: str):
    query = normalize_query(query)
    forms = sorted(word_forms(query), key=len, reverse=True)
    alts = [r"\s+".join(re.escape(p) for p in f.split()) for f in forms]
    return re.compile(
        r"(?<!\w)(?<!\w['’])(?:" + "|".join(alts)
        + r")(?!\w)(?!['’](?!s\b)\w)",
        re.IGNORECASE,
    )


def find_occurrences(
    sentences: List[str], query: str, limit: int
) -> Tuple[List[Occurrence], bool]:
    """First match per sentence; exact forms first; returns (occurrences, truncated)."""
    query = normalize_query(query)
    if not query.split():
        return [], False
    rx = _build_regex(query)
    exact_norm = " ".join(query.lower().split())
    result: List[Occurrence] = []
    for i, s in enumerate(sentences):
        m = None
        for cand in rx.finditer(s):
            if m is None:
                m = cand
            if " ".join(cand.group(0).lower().split()) == exact_norm:
                m = cand
                break
        if m is None:
            continue
        found = m.group(0)
        result.append(
            Occurrence(i, s, found, m.start(), m.end(),
                       " ".join(found.lower().split()) == exact_norm)
        )
    result.sort(key=lambda o: not o.exact)  # stable: book order within groups
    if len(result) > limit:
        return result[:limit], True
    return result, False


def mark_match(occ: Occurrence) -> str:
    s = occ.sentence
    esc = lambda t: html.escape(t, quote=False)
    if occ.start == occ.end:  # hand-typed sentence without the word: no empty <b>
        return esc(s)
    return (esc(s[: occ.start]) + "<b>" + esc(s[occ.start : occ.end])
            + "</b>" + esc(s[occ.end :]))
