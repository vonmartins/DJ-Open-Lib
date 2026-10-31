import dataclasses
import datetime

import pytest

from tunedex.model.beatgrid import BeatGrid, BeatMarker
from tunedex.model.cue import Cue, CueKind
from tunedex.model.errors import ValidationError
from tunedex.model.key import Key, Mode
from tunedex.model.track import DATE_FIELDS, INT_FIELDS, TEXT_FIELDS, Track

PATH = "/music/Artist/Track.mp3"


def test_minimal_track() -> None:
    track = Track(path_origin=PATH)

    for name in (*TEXT_FIELDS, *INT_FIELDS, *DATE_FIELDS, "bpm", "key", "color"):
        assert getattr(track, name) is None, name
    assert (track.tags, track.cues, track.beatgrid, dict(track.unmapped)) == ((), (), None, {})


def test_full_track() -> None:
    track = Track(
        path_origin=r"c:\Music\Artist\Track.mp3",
        title="Title",
        artist="Artist",
        bpm=128,
        key=Key(tonic=9, mode=Mode.MINOR),
        key_original="8A",
        rating=5,
        color="#00ff00",
        date_added=datetime.date(2026, 1, 2),
        last_played=datetime.datetime(2026, 1, 3, 22, 30),
        duration_us=360_000_000,
        energy=7,
        tags=("Techno",),
        cues=(Cue(kind=CueKind.HOT, start_us=0, slot=0),),
        beatgrid=BeatGrid(markers=(BeatMarker(position_us=0, bpm=128.0),)),
        unmapped={"traktor": {"LOCK": "1"}},
    )

    assert track.path == "C:/Music/Artist/Track.mp3"
    assert track.path_origin == r"c:\Music\Artist\Track.mp3"
    assert track.bpm == 128.0 and isinstance(track.bpm, float)
    assert track.color == "#00FF00"
    assert track.key == Key(tonic=9, mode=Mode.MINOR)
    assert track.key_original == "8A"
    assert track.unmapped == {"traktor": {"LOCK": "1"}}


def test_relative_path_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Track(path_origin="Music/Track.mp3")
    assert (excinfo.value.entity, excinfo.value.field) == ("Track", "path")


# Stable identity


def test_new_track_gets_identifier() -> None:
    assert Track(path_origin=PATH).id != Track(path_origin=PATH).id


def test_identifier_survives_a_move() -> None:
    track = Track(path_origin=PATH)
    moved = dataclasses.replace(track, path_origin="/other/Track.mp3")

    assert moved.id == track.id
    assert moved.path == "/other/Track.mp3"


# Field value ranges


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("rating", 6),
        ("rating", -1),
        ("energy", 11),
        ("danceability", -1),
        ("happiness", 11),
        ("popularity", 11),
        ("play_count", -1),
        ("bitrate", -1),
        ("sample_rate", -1),
        ("year", -1),
        ("track_number", -1),
        ("disc_number", -1),
        ("duration_us", -1),
        ("rating", 4.5),
        ("bpm", 0),
        ("bpm", -128.0),
        ("color", "red"),
        ("color", "#12345"),
        ("title", 5),
        ("date_added", datetime.datetime(2026, 1, 1)),
        ("date_added", "2026-01-01"),
        ("last_played", datetime.date(2026, 1, 1)),
        ("key", "Am"),
    ],
)
def test_out_of_range_rejected(name: str, value: object) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Track(path_origin=PATH, **{name: value})  # pyright: ignore[reportArgumentType]
    assert (excinfo.value.entity, excinfo.value.field) == ("Track", name)


# Tags


def test_duplicate_tags_dropped_keeping_order() -> None:
    assert Track(path_origin=PATH, tags=("Techno", "Vocals", "Techno")).tags == ("Techno", "Vocals")


def test_tags_are_case_sensitive() -> None:
    assert Track(path_origin=PATH, tags=("Techno", "techno")).tags == ("Techno", "techno")


@pytest.mark.parametrize("tag", ["", 3])
def test_invalid_tag_rejected(tag: object) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Track(path_origin=PATH, tags=("ok", tag))  # pyright: ignore[reportArgumentType]
    assert excinfo.value.field == "tags"


# Cues on a track


def test_duplicate_hot_cue_slot_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Track(
            path_origin=PATH,
            cues=(
                Cue(kind=CueKind.HOT, start_us=0, slot=1),
                Cue(kind=CueKind.HOT, start_us=5_000, slot=1),
            ),
        )
    assert excinfo.value.field == "cues"


def test_hot_loop_shares_slots_with_hot_cues() -> None:
    with pytest.raises(ValidationError):
        Track(
            path_origin=PATH,
            cues=(
                Cue(kind=CueKind.HOT, start_us=0, slot=2),
                Cue(kind=CueKind.LOOP, start_us=0, end_us=1_000, slot=2),
            ),
        )


def test_memory_cues_have_no_slot_conflict() -> None:
    track = Track(
        path_origin=PATH,
        cues=(Cue(kind=CueKind.MEMORY, start_us=0), Cue(kind=CueKind.MEMORY, start_us=0)),
    )
    assert len(track.cues) == 2


# Immutability


def test_update_produces_a_new_value() -> None:
    track = Track(path_origin=PATH, title="Old")
    updated = dataclasses.replace(track, title="New")

    assert (track.title, updated.title) == ("Old", "New")
    assert updated.id == track.id


def test_fields_cannot_be_assigned() -> None:
    track = Track(path_origin=PATH)
    with pytest.raises(dataclasses.FrozenInstanceError):
        track.title = "x"  # pyright: ignore[reportAttributeAccessIssue]


def test_replace_revalidates() -> None:
    with pytest.raises(ValidationError):
        dataclasses.replace(Track(path_origin=PATH), rating=9)


def test_equal_fields_compare_equal() -> None:
    track = Track(path_origin=PATH, title="T", tags=("a",))
    assert dataclasses.replace(track) == track
