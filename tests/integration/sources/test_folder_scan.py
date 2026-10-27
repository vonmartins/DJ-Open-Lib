import dataclasses
import datetime
import os
from pathlib import Path

import pytest

from djlib.model.cue import Cue, CueKind
from djlib.model.playlist import Playlist
from djlib.model.track import Track
from djlib.sources.folder_scan import scan_folder
from djlib.sources.scan_plan import (
    AddTrack,
    MarkMissing,
    MarkPresent,
    MoveTrack,
    RefreshState,
    ScanPlan,
    UpdateTrack,
)
from djlib.store import Store
from support.adapter_contract import tree_state
from support.audio import tagged_copy, write_tags

NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.UTC)


def scan(store: Store, root: Path) -> ScanPlan:
    return scan_folder(store, root, clock=lambda: NOW)


def scan_and_apply(store: Store, root: Path) -> ScanPlan:
    plan = scan(store, root)
    store.apply_scan(plan.operations)
    return plan


def kinds(plan: ScanPlan) -> list[str]:
    return [type(op).__name__ for op in plan.operations]


def bump_mtime(path: Path) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))


@pytest.fixture
def music(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    tagged_copy(root, "mp3", name="a.mp3", title="A", artist="Artist", genre="House")
    tagged_copy(root / "sub", "flac", name="b.flac", title="B")
    return root


# New tracks and incremental rescans


def test_first_scan_adds_every_file(store: Store, music: Path) -> None:
    plan = scan_and_apply(store, music)

    assert kinds(plan) == ["AddTrack", "AddTrack"]
    added = store.find_track_by_path(str(music / "a.mp3"))
    assert added is not None
    assert (added.title, added.artist, added.genre, added.file_format) == (
        "A",
        "Artist",
        "House",
        "mp3",
    )
    assert added.date_added == NOW.date()
    expected_modified = datetime.datetime.fromtimestamp(
        (music / "a.mp3").stat().st_mtime, datetime.UTC
    ).date()
    assert added.date_modified == expected_modified


def test_root_as_relative_string(
    store: Store, music: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan_and_apply(store, music)
    monkeypatch.chdir(music.parent)

    plan = scan_folder(store, "./music", clock=lambda: NOW)

    assert plan.operations == ()
    assert plan.root == music


def test_nothing_changed(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    assert scan(store, music).operations == ()


def test_one_new_file(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    tagged_copy(music / "sub", "ogg", name="c.ogg", title="C")

    plan = scan(store, music)

    assert kinds(plan) == ["AddTrack"]
    operation = plan.operations[0]
    assert isinstance(operation, AddTrack) and operation.track.title == "C"


def test_touched_but_identical(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    bump_mtime(music / "a.mp3")

    plan = scan_and_apply(store, music)

    assert kinds(plan) == ["RefreshState"]
    assert scan(store, music).operations == ()


def test_scanning_is_read_only(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    write_tags(music / "a.mp3", title="Changed")
    files_before, library_before = tree_state(music), store.load_library()
    states_before = store.file_states(str(music))

    scan(store, music)

    assert tree_state(music) == files_before
    assert store.load_library() == library_before
    assert store.file_states(str(music)) == states_before


# Three-way merge


def test_tag_edited_in_the_file(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    write_tags(music / "a.mp3", title="New title")

    plan = scan_and_apply(store, music)

    assert kinds(plan) == ["UpdateTrack"] and plan.conflicts == ()
    track = store.find_track_by_path(str(music / "a.mp3"))
    assert track is not None and track.title == "New title"


def test_edited_in_djlib_only(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    track = store.find_track_by_path(str(music / "a.mp3"))
    assert track is not None
    store.update_track(dataclasses.replace(track, genre="Deep House"))
    write_tags(music / "a.mp3", title="New title")

    plan = scan_and_apply(store, music)

    updated = store.get_track(track.id)
    assert (updated.genre, updated.title) == ("Deep House", "New title")
    assert plan.conflicts == ()


def test_edited_on_both_sides(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    track = store.find_track_by_path(str(music / "a.mp3"))
    assert track is not None
    store.update_track(dataclasses.replace(track, artist="Fixed Artist"))
    write_tags(music / "a.mp3", artist="Tag Artist")

    plan = scan_and_apply(store, music)

    assert store.get_track(track.id).artist == "Fixed Artist"
    (conflict,) = plan.conflicts
    assert (conflict.track_id, conflict.field) == (track.id, "artist")
    assert (conflict.library_value, conflict.file_value) == ("Fixed Artist", "Tag Artist")

    bump_mtime(music / "a.mp3")
    assert scan(store, music).conflicts == ()


def test_track_without_file_state_fills_empty_fields(store: Store, music: Path) -> None:
    existing = Track(path_origin=str(music / "a.mp3"), title="Kept title")
    store.add_track(existing)

    plan = scan_and_apply(store, music)

    assert "UpdateTrack" in kinds(plan)
    track = store.get_track(existing.id)
    assert (track.title, track.artist) == ("Kept title", "Artist")


# Moves, missing and present


def test_file_renamed(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    track = store.find_track_by_path(str(music / "a.mp3"))
    assert track is not None
    with_cue = dataclasses.replace(track, cues=(Cue(kind=CueKind.HOT, start_us=100, slot=0),))
    store.update_track(with_cue)
    store.add_node(Playlist(name="Set", entries=(track.id,)))
    (music / "a.mp3").rename(music / "sub" / "renamed.mp3")

    plan = scan_and_apply(store, music)

    assert kinds(plan) == ["MoveTrack"]
    operation = plan.operations[0]
    assert isinstance(operation, MoveTrack)
    moved = store.get_track(track.id)
    assert moved.path.endswith("/sub/renamed.mp3")
    assert moved.cues == with_cue.cues
    (playlist,) = store.children()
    assert playlist.entries == (track.id,)  # pyright: ignore[reportAttributeAccessIssue]


def test_ambiguous_move_is_added_with_warning(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "music"
    first = tagged_copy(root, "mp3", name="one.mp3")
    second = tagged_copy(root, "mp3", name="two.mp3")
    scan_and_apply(store, root)
    copy = first.read_bytes()
    first.unlink()
    second.unlink()
    (root / "three.mp3").write_bytes(copy)

    plan = scan(store, root)

    assert kinds(plan) == ["AddTrack", "MarkMissing", "MarkMissing"]
    assert any("several missing tracks" in w for w in plan.warnings)


def test_file_deleted_and_back(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    track = store.find_track_by_path(str(music / "a.mp3"))
    assert track is not None
    store.add_node(Playlist(name="Set", entries=(track.id,)))
    content = (music / "a.mp3").read_bytes()
    stat = (music / "a.mp3").stat()
    (music / "a.mp3").unlink()

    plan = scan_and_apply(store, music)

    assert plan.operations == (MarkMissing(track.id),)
    state = store.file_state(track.id)
    assert state is not None and state.missing
    assert store.children()[0].entries == (track.id,)  # pyright: ignore[reportAttributeAccessIssue]
    assert scan(store, music).operations == ()

    (music / "a.mp3").write_bytes(content)
    os.utime(music / "a.mp3", ns=(stat.st_atime_ns, stat.st_mtime_ns))
    plan = scan_and_apply(store, music)

    assert kinds(plan) == ["MarkPresent"]
    operation = plan.operations[0]
    assert isinstance(operation, MarkPresent) and not operation.state.missing
    state = store.file_state(track.id)
    assert state is not None and not state.missing


def test_other_roots_untouched(store: Store, tmp_path: Path) -> None:
    a, b = tmp_path / "music" / "a", tmp_path / "music" / "ab"
    tagged_copy(a, "mp3", name="x.mp3")
    tagged_copy(b, "mp3", name="y.mp3")
    scan_and_apply(store, b)

    plan = scan(store, a)

    assert kinds(plan) == ["AddTrack"]
    assert all(not isinstance(op, MarkMissing) for op in plan.operations)


def test_changed_file_that_was_missing_becomes_present(store: Store, music: Path) -> None:
    scan_and_apply(store, music)
    track = store.find_track_by_path(str(music / "a.mp3"))
    assert track is not None
    store.apply_scan([MarkMissing(track.id)])
    write_tags(music / "a.mp3", title="Back")

    plan = scan_and_apply(store, music)

    assert any(isinstance(op, UpdateTrack | RefreshState) for op in plan.operations)
    state = store.file_state(track.id)
    assert state is not None and not state.missing
