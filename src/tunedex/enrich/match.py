"""Deciding which MusicBrainz recording a track is, from AcoustID's answer. Never guesses."""

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from tunedex.enrich.acoustid import Candidate, Lookup

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


@dataclass(frozen=True, slots=True)
class Mismatch:
    """AcoustID's recording does not fit the track's artist, title or file name."""

    candidate: Candidate


Outcome = Identified | Unresolved | NotRecognized | Unlinked | Disagreement | Mismatch

# Words that say nothing about which song a track is.
_STOP_WORDS = frozenset(
    {
        "original", "mix", "remix", "edit", "extended", "feat", "the", "and", "version",
        "vip", "dub", "radio", "club", "rmx", "mp3", "wav", "flac", "remastered", "official",
        "video", "audio", "free", "download", "www", "com",
    }
)  # fmt: skip
_WORD = re.compile(r"[^\W_]{3,}")


def comparable(title: str | None) -> str:
    """A title without bracketed parts, case or punctuation, to compare titles."""
    text = _BRACKETS.sub(" ", unicodedata.normalize("NFKC", title or "")).casefold()
    return "".join(c for c in text if c.isalnum())


def words(*texts: str | None) -> set[str]:
    """The telling words of ``texts``: three or more letters or digits, without case,
    accents or stop words."""
    found: set[str] = set()
    for text in texts:
        plain = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text or ""))
        plain = "".join(c for c in plain if not unicodedata.combining(c)).casefold()
        found.update(w for w in _WORD.findall(plain) if w not in _STOP_WORDS)
    return found


def identify(
    lookup: Lookup,
    *,
    duration: float | None,
    title: str | None,
    carried_id: str | None,
    first_release: Callable[[str], str | None],
    artist: str | None = None,
    file_name: str | None = None,
) -> Outcome:
    """Which recording the track is.

    ``first_release`` gives a recording's earliest official release date. A recording
    that does not fit the track's ``title``, ``artist`` or ``file_name`` (see ``agrees``)
    is a ``Mismatch``.
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
    if carried_id is None and not agrees(chosen, title=title, artist=artist, file_name=file_name):
        return Mismatch(chosen)
    return Identified(chosen.recording_id, chosen.score)


def agrees(
    candidate: Candidate, *, title: str | None, artist: str | None, file_name: str | None
) -> bool:
    """Whether a recording fits what the track says about itself.

    A track with an artist (in its tags, or before `` - `` in its file name) must share
    a word with the recording's artist. Otherwise its title or file name must share one
    with the recording's title, without bracketed parts, or artist. A track with no
    words at all fits any recording.
    """
    named, sep, rest = (file_name or "").partition(" - ")
    own_artist = words(artist) or (words(named) if sep else set())
    if own_artist:
        return bool(own_artist & words(candidate.artist))
    own = words(title, rest if sep else file_name)
    found = words(_BRACKETS.sub(" ", candidate.title or ""), candidate.artist)
    return not own or bool(own & found)


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
