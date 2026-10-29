"""What a kept track inherits from its duplicates (specs/duplicates)."""

import datetime

from djlib.duplicates.merging import merge
from djlib.model.beatgrid import BeatGrid, BeatMarker
from djlib.model.cue import Cue, CueKind
from djlib.model.track import Track

CUES = tuple(Cue(kind=CueKind.HOT, start_us=i * 1_000_000, slot=i) for i in range(4))
GRID = BeatGrid(markers=(BeatMarker(position_us=0, bpm=140.0),))


def test_empty_fields_filled() -> None:
    kept = Track(path_origin="/m/a.flac", title="Numb", file_format="flac", bitrate=900)
    other = Track(
        path_origin="/m/b.mp3", title="numb", label="Tempa", file_format="mp3", bitrate=128
    )

    merged = merge(kept, [other])

    assert (merged.title, merged.label) == ("Numb", "Tempa")
    assert (merged.file_format, merged.bitrate, merged.path) == ("flac", 900, "/m/a.flac")


def test_first_other_wins() -> None:
    kept = Track(path_origin="/m/a.flac")
    first = Track(path_origin="/m/b.mp3", genre="Dubstep")
    second = Track(path_origin="/m/c.mp3", genre="Ambient", label="Tempa")

    merged = merge(kept, [first, second])

    assert (merged.genre, merged.label) == ("Dubstep", "Tempa")


def test_play_counts_and_cues() -> None:
    kept = Track(path_origin="/m/a.flac", play_count=3)
    other = Track(path_origin="/m/b.mp3", play_count=5, cues=CUES, beatgrid=GRID)

    merged = merge(kept, [other])

    assert (merged.cues, merged.beatgrid, merged.play_count) == (CUES, GRID, 8)


def test_own_cues_kept() -> None:
    kept = Track(path_origin="/m/a.flac", cues=CUES[:1])
    other = Track(path_origin="/m/b.mp3", cues=CUES)

    assert merge(kept, [other]).cues == CUES[:1]


def test_combined_fields() -> None:
    kept = Track(
        path_origin="/m/a.flac",
        rating=3,
        date_added=datetime.date(2024, 5, 1),
        last_played=datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        tags=("warmup",),
    )
    other = Track(
        path_origin="/m/b.mp3",
        rating=5,
        date_added=datetime.date(2019, 3, 2),
        last_played=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        tags=("peak", "warmup"),
    )

    merged = merge(kept, [other])

    assert merged.rating == 5
    assert merged.date_added == datetime.date(2019, 3, 2)
    assert merged.last_played == other.last_played
    assert merged.tags == ("warmup", "peak")


def test_kept_values_never_overwritten() -> None:
    kept = Track(path_origin="/m/a.flac", title="Numb", artist="Phaeleh", bpm=140.0, label="A")
    other = Track(path_origin="/m/b.mp3", title="Numb (x)", artist="P", bpm=70.0, label="B")

    assert merge(kept, [other]) == kept


def test_unmapped_not_merged() -> None:
    kept = Track(path_origin="/m/a.flac")
    other = Track(path_origin="/m/b.mp3", unmapped={"mixxx": {"id": 4}})

    assert merge(kept, [other]).unmapped == {}
