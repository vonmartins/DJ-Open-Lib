"""Which track of a group to keep, and why."""

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tunedex.model.ids import TrackId
from tunedex.model.track import Track

LOSSLESS = frozenset({"flac", "wav", "aiff", "alac", "ape"})
REASONS = (
    "file present",
    "lossless",
    "bitrate",
    "cues",
    "beat grid",
    "playlists",
    "oldest",
    "path",
)


@dataclass(frozen=True, slots=True)
class Facts:
    """What ranking needs to know besides the track itself."""

    present: bool
    playlists: int


@dataclass(frozen=True, slots=True)
class Ranked:
    tracks: tuple[Track, ...]
    """Best first: the first one is the suggested track to keep."""
    reason: str
    """The criterion that put the first track ahead of the second."""


def rank(tracks: Sequence[Track], facts: Mapping[TrackId, Facts]) -> Ranked:
    """Order a group of two or more tracks from the one to keep to the last."""
    ordered = sorted(tracks, key=lambda t: _key(t, facts[t.id]))
    first, second = _key(ordered[0], facts[ordered[0].id]), _key(ordered[1], facts[ordered[1].id])
    reason = next(
        (name for name, a, b in zip(REASONS, first, second, strict=True) if a != b), "path"
    )
    return Ranked(tracks=tuple(ordered), reason=reason)


def _key(track: Track, facts: Facts) -> tuple[bool, bool, int, int, bool, int, int, str]:
    added = track.date_added or datetime.date.max
    return (
        not facts.present,
        (track.file_format or "").lower() not in LOSSLESS,
        -(track.bitrate or 0),
        -len(track.cues),
        track.beatgrid is None,
        -facts.playlists,
        added.toordinal(),
        track.path,
    )
