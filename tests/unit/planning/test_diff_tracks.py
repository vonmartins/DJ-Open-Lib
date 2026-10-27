import dataclasses
import datetime

from djlib.model.beatgrid import BeatGrid, BeatMarker
from djlib.model.cue import Cue, CueKind
from djlib.model.key import Key, Mode
from djlib.model.track import Track
from djlib.planning.diff import diff_tracks
from djlib.planning.model import FieldChange

BASE = Track(path_origin="/music/a.mp3", title="A", bpm=126.0)


def test_identical_tracks_have_no_changes() -> None:
    assert diff_tracks(BASE, dataclasses.replace(BASE)) == ()


def test_changed_scalar_fields() -> None:
    after = dataclasses.replace(BASE, bpm=128.0, title=None, year=2017)

    assert diff_tracks(BASE, after) == (
        FieldChange("title", "A", None),
        FieldChange("year", None, 2017),
        FieldChange("bpm", 126.0, 128.0),
    )


def test_keys_and_dates_are_model_values() -> None:
    a_minor = Key(tonic=9, mode=Mode.MINOR)
    after = dataclasses.replace(BASE, key=a_minor, date_added=datetime.date(2026, 1, 2))

    assert set(diff_tracks(BASE, after)) == {
        FieldChange("key", None, a_minor),
        FieldChange("date_added", None, datetime.date(2026, 1, 2)),
    }


def test_composite_fields_reported_once() -> None:
    cue = Cue(kind=CueKind.HOT, start_us=1_000_000, slot=0)
    grid = BeatGrid(markers=(BeatMarker(position_us=0, bpm=126.0, beat=1),))
    after = dataclasses.replace(BASE, tags=("Peak", "Dark"), cues=(cue,), beatgrid=grid)

    assert [c.field for c in diff_tracks(BASE, after)] == ["tags", "cues", "beatgrid"]


def test_restricted_fields() -> None:
    after = dataclasses.replace(BASE, bpm=128.0, title="B")

    assert diff_tracks(BASE, after, ["title"]) == (FieldChange("title", "A", "B"),)


def test_paths_and_ids_are_not_fields() -> None:
    moved = dataclasses.replace(BASE, path_origin="/music/b.mp3")

    assert diff_tracks(BASE, moved) == ()
