import dataclasses
import datetime
from pathlib import Path

from tunedex.model.track import Track
from tunedex.planning.diff import diff_scan
from tunedex.planning.model import FieldChange
from tunedex.sources.scan_plan import (
    AddTrack,
    MarkMissing,
    MarkPresent,
    MoveTrack,
    RefreshState,
    ScanPlan,
    UpdateTrack,
)
from tunedex.store import FileState, Store

ROOT = Path("/music")
NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.UTC)


def state(track: Track, *, missing: bool = False) -> FileState:
    return FileState(
        track_id=track.id,
        size=1,
        mtime_ns=1,
        quick_hash="c" * 64,
        scanned_at=NOW,
        missing=missing,
        scanned_values={},
    )


def test_field_change_shown(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", artist="X", title="Y", bpm=126.0)
    store.apply_scan([AddTrack(track, state(track))])
    edited = dataclasses.replace(track, bpm=128.0)

    changes, _ = diff_scan(
        store, ScanPlan(root=ROOT, operations=(UpdateTrack(edited, state(edited)),))
    )

    (change,) = changes
    assert (change.change, change.name, change.path) == ("updated", "X - Y", "/music/a.mp3")
    assert change.fields == (FieldChange("bpm", 126.0, 128.0),)


def test_every_operation_kind(store: Store) -> None:
    moved, gone, back, touched = (Track(path_origin=f"/music/{n}.mp3") for n in "mgbt")
    for track in (moved, gone, back, touched):
        store.apply_scan([AddTrack(track, state(track))])
    new = Track(path_origin="/music/new.mp3", title="New")
    relocated = dataclasses.replace(moved, path_origin="/music/sub/m.mp3", title="M")
    operations = (
        MoveTrack(relocated, state(relocated), old_path=moved.path),
        AddTrack(new, state(new)),
        MarkMissing(gone.id),
        MarkPresent(back.id, state(back)),
        RefreshState(touched.id, state(touched)),
    )

    changes, refreshed = diff_scan(store, ScanPlan(root=ROOT, operations=operations))

    assert [(c.change, c.path) for c in changes] == [
        ("moved", "/music/sub/m.mp3"),
        ("added", "/music/new.mp3"),
        ("missing", "/music/g.mp3"),
        ("present", "/music/b.mp3"),
    ]
    assert changes[0].old_path == "/music/m.mp3"
    assert changes[0].fields == (FieldChange("title", None, "M"),)
    assert changes[1].name == "New"
    assert refreshed == 1
