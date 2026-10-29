"""Deciding which MusicBrainz recording a track is, from AcoustID's answer. Never guesses."""

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from djlib.enrich.acoustid import Candidate, Lookup

MIN_SCORE = 0.85
MAX_LENGTH_GAP = 7.0  # seconds
_BRACKETS = re.compile(r"[\(\[][^\(\)\[\]]*[\)\]]")


@dataclass(frozen=True, slots=True)
class Identified:
    recording_id: str
    score: float


@dataclass(frozen=True, slots=True)
class Unresolved:
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True, slots=True)
class NotRecognized:
    best_score: float


@dataclass(frozen=True, slots=True)
class Unlinked:
    """AcoustID knows the sound, but no MusicBrainz recording is linked to it."""

    best_score: float


@dataclass(frozen=True, slots=True)
class Disagreement:
    carried: str
    found: str


Outcome = Identified | Unresolved | NotRecognized | Unlinked | Disagreement


def comparable(title: str | None) -> str:
    """A title without bracketed parts, case or punctuation, to compare titles."""
    text = _BRACKETS.sub(" ", unicodedata.normalize("NFKC", title or "")).casefold()
    return "".join(c for c in text if c.isalnum())


def identify(
    lookup: Lookup,
    *,
    duration: float | None,
    title: str | None,
    carried_id: str | None,
    first_release: Callable[[str], str | None],
) -> Outcome:
    """Which recording the track is.

    ``first_release`` gives a recording's earliest official release date.
    """
    candidates = [c for c in lookup.candidates if c.score >= MIN_SCORE]
    if not candidates:
        if lookup.best_score >= MIN_SCORE:
            return Unlinked(lookup.best_score)
        return NotRecognized(lookup.best_score)
    chosen = _choose(candidates, duration, title, first_release)
    if chosen is None:
        return Unresolved(tuple(candidates[:5]))
    if carried_id and carried_id != chosen.recording_id:
        return Disagreement(carried_id, chosen.recording_id)
    return Identified(chosen.recording_id, chosen.score)


def _choose(
    candidates: Sequence[Candidate],
    duration: float | None,
    title: str | None,
    first_release: Callable[[str], str | None],
) -> Candidate | None:
    if len(candidates) == 1:
        return candidates[0]
    kept = list(candidates)
    if duration:
        kept = [
            c for c in kept if c.duration is None or abs(c.duration - duration) <= MAX_LENGTH_GAP
        ]
    wanted = comparable(title)
    if wanted:
        titled = [
            c for c in kept
            if (got := comparable(c.title)) and (got.startswith(wanted) or wanted.startswith(got))
        ]  # fmt: skip
        kept = titled or kept
    if len(kept) == 1:
        return kept[0]
    if kept and len({(comparable(c.title), (c.artist or "").casefold()) for c in kept}) == 1:
        # The same song recorded twice in MusicBrainz (different compilations).
        return min(kept, key=lambda c: (first_release(c.recording_id) or "9999", c.recording_id))
    return None
