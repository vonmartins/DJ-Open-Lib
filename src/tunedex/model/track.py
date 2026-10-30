"""Tracks: one audio file and everything known about it."""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field

from tunedex.model._validate import (
    check_color,
    check_int,
    check_positive_float,
    check_text,
    set_field,
)
from tunedex.model.beatgrid import BeatGrid
from tunedex.model.cue import Cue
from tunedex.model.errors import ValidationError
from tunedex.model.ids import TrackId, new_track_id
from tunedex.model.key import Key
from tunedex.model.paths import normalize_path
from tunedex.model.unmapped import JSONValue, copy_unmapped

TEXT_FIELDS = (
    "title",
    "artist",
    "album",
    "album_artist",
    "original_artist",
    "genre",
    "comment",
    "grouping",
    "composer",
    "producer",
    "lyricist",
    "remixer",
    "mix",
    "label",
    "file_format",
    "key_original",
    "extra1",
    "extra2",
)
# Field name -> (minimum, maximum) for integer fields.
INT_FIELDS: dict[str, tuple[int, int | None]] = {
    "year": (0, None),
    "track_number": (0, None),
    "disc_number": (0, None),
    "rating": (0, 5),
    "play_count": (0, None),
    "duration_us": (0, None),
    "bitrate": (0, None),
    "sample_rate": (0, None),
    "energy": (0, 10),
    "danceability": (0, 10),
    "happiness": (0, 10),
    "popularity": (0, 10),
}
DATE_FIELDS = ("date_added", "date_modified", "release_date")


@dataclass(frozen=True, slots=True, kw_only=True)
class Track:
    """A track in the canonical library.

    ``path_origin`` is the path exactly as received; ``path`` is derived from it
    (see ``normalize_path``) and is the identity key used to recognize the same
    file across imports. ``id`` never changes, even when the path does.
    """

    path_origin: str
    id: TrackId = field(default_factory=new_track_id)
    path: str = field(init=False)

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    original_artist: str | None = None
    genre: str | None = None
    year: int | None = None
    track_number: int | None = None
    disc_number: int | None = None
    bpm: float | None = None
    key: Key | None = None
    key_original: str | None = None
    rating: int | None = None
    color: str | None = None
    comment: str | None = None
    grouping: str | None = None
    composer: str | None = None
    producer: str | None = None
    lyricist: str | None = None
    remixer: str | None = None
    mix: str | None = None
    label: str | None = None
    play_count: int | None = None
    date_added: datetime.date | None = None
    date_modified: datetime.date | None = None
    release_date: datetime.date | None = None
    last_played: datetime.datetime | None = None
    duration_us: int | None = None
    bitrate: int | None = None
    sample_rate: int | None = None
    file_format: str | None = None
    energy: int | None = None
    danceability: int | None = None
    happiness: int | None = None
    popularity: int | None = None
    extra1: str | None = None
    extra2: str | None = None

    tags: tuple[str, ...] = ()
    cues: tuple[Cue, ...] = ()
    beatgrid: BeatGrid | None = None
    unmapped: Mapping[str, JSONValue] = field(default_factory=dict[str, JSONValue])

    def __post_init__(self) -> None:
        check_text("Track", "path_origin", self.path_origin)
        set_field(self, "path", normalize_path(self.path_origin))

        for name in TEXT_FIELDS:
            check_text("Track", name, getattr(self, name))
        for name, (minimum, maximum) in INT_FIELDS.items():
            check_int("Track", name, getattr(self, name), minimum=minimum, maximum=maximum)
        for name in DATE_FIELDS:
            value = getattr(self, name)
            if value is not None and type(value) is not datetime.date:
                raise ValidationError("Track", name, "must be a date")
        if self.last_played is not None and not isinstance(self.last_played, datetime.datetime):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Track", "last_played", "must be a datetime")

        set_field(self, "bpm", check_positive_float("Track", "bpm", self.bpm))
        set_field(self, "color", check_color("Track", "color", self.color))
        if self.key is not None and not isinstance(self.key, Key):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Track", "key", "must be a Key")
        if self.beatgrid is not None and not isinstance(self.beatgrid, BeatGrid):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Track", "beatgrid", "must be a BeatGrid")

        set_field(self, "tags", _dedupe_tags(self.tags))
        set_field(self, "cues", _check_cues(self.cues))
        set_field(self, "unmapped", copy_unmapped(self.unmapped, entity="Track"))


def _dedupe_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for tag in tags:
        if not isinstance(tag, str) or not tag:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Track", "tags", "tags must be non-empty text")
        seen.setdefault(tag, None)
    return tuple(seen)


def _check_cues(cues: tuple[Cue, ...]) -> tuple[Cue, ...]:
    cues = tuple(cues)
    slots: set[int] = set()
    for cue in cues:
        if not isinstance(cue, Cue):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Track", "cues", "must contain Cue values")
        if cue.slot is not None:
            if cue.slot in slots:
                raise ValidationError("Track", "cues", f"hot-cue slot {cue.slot} is used twice")
            slots.add(cue.slot)
    return cues
