import dataclasses
import os
from pathlib import Path

import pytest

from djlib.planning import ApplyFailedError, Engine, StaleTargetError, assume_yes
from djlib.snapshots import SnapshotStore
from djlib.store import FileState, Store
from support.audio import tagged_copy, write_tags
from support.files import tree_bytes


@pytest.fixture
def music(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    tagged_copy(root, "mp3", name="a.mp3", title="A", artist="Artist", bpm="126")
    tagged_copy(root / "sub", "flac", name="b.flac", title="B")
    return root


def content(store: Store) -> object:
    tracks = store.list_tracks()
    return tracks, {t.id: store.file_state(t.id) for t in tracks}, store.load_library()


def test_scan_planned_writes_nothing(
    engine: Engine, store: Store, music: Path, tmp_path: Path
) -> None:
    revision, before = store.revision(), content(store)

    plan = engine.plan_scan(music)

    assert [t.change for t in plan.tracks] == ["added", "added"]
    assert store.revision() == revision
    assert content(store) == before
    assert tree_bytes(tmp_path / "snapshots") == {}


def test_scan_applied_with_snapshot(
    engine: Engine, snapshots: SnapshotStore, store: Store, music: Path
) -> None:
    plan = engine.plan_scan(music)

    result = engine.apply(plan, assume_yes)

    assert (result.status, result.operations_applied) == ("applied", 2)
    assert len(store.list_tracks()) == 2
    (snapshot,) = snapshots.list("library")
    assert snapshot.id == result.snapshot
    assert [r.method for r in snapshot.files] == ["sqlite"]


def test_field_change_shown(engine: Engine, music: Path) -> None:
    engine.apply(engine.plan_scan(music), assume_yes)
    write_tags(music / "a.mp3", bpm="128")
    stat = (music / "a.mp3").stat()
    os.utime(music / "a.mp3", ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    plan = engine.plan_scan(music)

    (change,) = plan.tracks
    assert (change.change, change.label) == ("updated", "Artist - A")
    assert [(f.field, f.before, f.after) for f in change.fields] == [("bpm", 126.0, 128.0)]


def test_conflicts_carry_labels(engine: Engine, store: Store, music: Path) -> None:
    engine.apply(engine.plan_scan(music), assume_yes)
    track = store.find_track_by_path(str(music / "a.mp3"))
    assert track is not None
    store.update_track(dataclasses.replace(track, bpm=125.0))
    write_tags(music / "a.mp3", bpm="128")
    stat = (music / "a.mp3").stat()
    os.utime(music / "a.mp3", ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    (conflict,) = engine.plan_scan(music).conflicts

    assert (conflict.label, conflict.field, conflict.library_value, conflict.file_value) == (
        "Artist - A",
        "bpm",
        125.0,
        128.0,
    )


def test_library_edited_after_planning(engine: Engine, store: Store, music: Path) -> None:
    plan = engine.plan_scan(music)
    store.add_track(dataclasses.replace(plan.action.operations[0].track, path_origin="/x.mp3"))  # pyright: ignore[reportAttributeAccessIssue]
    revision, before = store.revision(), content(store)

    with pytest.raises(StaleTargetError, match="library changed"):
        engine.apply(plan, assume_yes)

    assert (store.revision(), content(store)) == (revision, before)


def test_fault_in_the_middle_of_a_scan_apply(
    engine: Engine, store: Store, music: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine.apply(engine.plan_scan(music), assume_yes)
    tagged_copy(music, "ogg", name="c.ogg", title="C")
    tagged_copy(music, "m4a", name="d.m4a", title="D")
    plan = engine.plan_scan(music)
    assert [t.change for t in plan.tracks] == ["added", "added"]
    revision, before = store.revision(), content(store)
    original = Store._put_file_state  # pyright: ignore[reportPrivateUsage]
    calls: list[FileState] = []

    def fail_on_second(self: Store, state: FileState) -> None:
        calls.append(state)
        if len(calls) == 2:
            raise OSError("injected failure")
        original(self, state)

    monkeypatch.setattr(Store, "_put_file_state", fail_on_second)

    with pytest.raises(ApplyFailedError, match="restored") as excinfo:
        engine.apply(plan, assume_yes)

    assert excinfo.value.restored
    assert len(calls) == 2
    assert (store.revision(), content(store)) == (revision, before)


def test_scan_twice(engine: Engine, music: Path) -> None:
    engine.apply(engine.plan_scan(music), assume_yes)

    plan = engine.plan_scan(music)

    assert plan.empty
    assert engine.apply(plan, assume_yes).status == "nothing"
