"""Beatgrids: tempo markers along a track."""

import itertools
from dataclasses import dataclass

from djlib.model._validate import check_int, check_positive_float, set_field
from djlib.model.errors import ValidationError


@dataclass(frozen=True, slots=True, kw_only=True)
class BeatMarker:
    """A grid anchor: from ``position_us`` on, beats follow at ``bpm``.

    ``beat`` is the position of this beat within the bar (1 to 4).
    """

    position_us: int
    bpm: float
    beat: int = 1

    def __post_init__(self) -> None:
        check_int("BeatMarker", "position_us", self.position_us, minimum=0, required=True)
        bpm = check_positive_float("BeatMarker", "bpm", self.bpm)
        if bpm is None:
            raise ValidationError("BeatMarker", "bpm", "is required")
        set_field(self, "bpm", bpm)
        check_int("BeatMarker", "beat", self.beat, minimum=1, maximum=4)


@dataclass(frozen=True, slots=True, kw_only=True)
class BeatGrid:
    """One or more markers with strictly increasing positions.

    Several markers represent tempo changes.
    """

    markers: tuple[BeatMarker, ...]

    def __post_init__(self) -> None:
        markers = tuple(self.markers)
        if not markers:
            raise ValidationError("BeatGrid", "markers", "must contain at least one marker")
        if any(not isinstance(m, BeatMarker) for m in markers):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("BeatGrid", "markers", "must contain BeatMarker values")
        positions = [m.position_us for m in markers]
        if any(a >= b for a, b in itertools.pairwise(positions)):
            raise ValidationError("BeatGrid", "markers", "positions must be strictly increasing")
        set_field(self, "markers", markers)
