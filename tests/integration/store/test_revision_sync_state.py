import datetime
import sqlite3
from pathlib import Path

import pytest

from djlib.model.ids import NodeId
from djlib.model.playlist import Folder, Playlist
from djlib.model.track import Track
from djlib.store import ConflictError, FileState, NotFoundError, Store
from djlib.store.migrations import bundled_migrations, schema_version
from djlib.store.operations import AddTrack, MarkMissing
from support.store import old_database

NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.UTC)
TARGET = "m3u-1a2b3c4d5e6f"
FP_A, FP_B = "a" * 64, "b" * 64


# Revision


def test_fresh_store_starts_at_zero(store: Store) -> None:
    assert store.revision() == 0


def test_write_increments(store: Store) -> None:
    store.add_track(Track(path_origin="/music/a.mp3"))
    before = store.revision()

    store.add_track(Track(path_origin="/music/b.mp3"))

    assert store.revision() > before


def test_every_content_write_increments(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3")
    playlist = Playlist(name="P", entries=(track.id,))
    writes = [
        lambda: store.add_track(track),
        lambda: store.update_track(track),
        lambda: store.add_node(playlist),
        lambda: store.update_node(playlist),
        lambda: store.delete_node(playlist.id),
        lambda: store.delete_track(track.id),
    ]
    for write in writes:
        before = store.revision()
        write()
        assert store.revision() > before


def test_failed_write_does_not(store: Store) -> None:
    store.add_track(Track(path_origin="/music/a.mp3"))
    before = store.revision()

    with pytest.raises(ConflictError):
        store.add_track(Track(path_origin="/music/a.mp3"))

    assert store.revision() == before


def test_reads_do_not(store: Store) -> None:
    store.add_track(Track(path_origin="/music/a.mp3"))
    before = store.revision()

    store.list_tracks()
    store.load_library()
    store.sync_state(TARGET)

    assert store.revision() == before


def test_revision_moved_on(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3")
    store.add_track(Track(path_origin="/music/other.mp3"))
    expected = store.revision() - 1

    with pytest.raises(ConflictError, match="changed since the plan"):
        store.apply_scan([AddTrack(track, _state(track))], expected_revision=expected)

    assert store.find_track_by_path(track.path) is None
    assert store.revision() == expected + 1


def test_expected_revision_matches(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3")
    revision = store.revision()

    store.apply_scan([AddTrack(track, _state(track))], expected_revision=revision)

    assert store.revision() > revision


def test_failed_scan_apply_keeps_revision(store: Store) -> None:
    revision = store.revision()
    track = Track(path_origin="/music/a.mp3")

    with pytest.raises(NotFoundError):
        store.apply_scan(
            [AddTrack(track, _state(track)), MarkMissing(Track(path_origin="/x.mp3").id)]
        )

    assert store.revision() == revision
    assert store.list_tracks() == []


def test_version_two_database_upgrades_with_backup(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    track = Track(path_origin="/music/old.mp3", title="Old")
    old_database(path, 2, [track])

    with Store.open(path) as store:
        assert store.get_track(track.id) == track
        assert schema_version(store._db) == bundled_migrations()[-1].version  # pyright: ignore[reportPrivateUsage]
        assert store.revision() == 0
    assert len(list(tmp_path.glob("library.db.v2-*.bak"))) == 1


# Sync state


def test_sync_state_round_trip(tmp_path: Path) -> None:
    a, b = Playlist(name="A"), Playlist(name="B")
    with Store.open(tmp_path / "library.db") as store:
        store.add_node(a)
        store.add_node(b)
        store.record_sync(TARGET, {a.id: FP_A, b.id: FP_B}, NOW)

    with Store.open(tmp_path / "library.db") as store:
        assert store.sync_state(TARGET) == {a.id: FP_A, b.id: FP_B}
        assert store.sync_state("m3u-000000000000") == {}


def test_recording_replaces_and_keeps_revision(store: Store) -> None:
    a = Playlist(name="A")
    store.add_node(a)
    store.record_sync(TARGET, {a.id: FP_A}, NOW)
    revision = store.revision()

    store.record_sync(TARGET, {a.id: FP_B}, NOW)

    assert store.sync_state(TARGET) == {a.id: FP_B}
    assert store.revision() == revision


def test_deleted_with_the_node(store: Store) -> None:
    a = Playlist(name="A")
    store.add_node(a)
    store.record_sync(TARGET, {a.id: FP_A}, NOW)

    store.delete_node(a.id)

    assert store.sync_state(TARGET) == {}


def test_updating_a_node_keeps_sync_state_of_remaining_nodes(store: Store) -> None:
    kept, dropped = Playlist(name="Kept"), Playlist(name="Dropped")
    folder = Folder(name="F", children=(kept, dropped))
    store.add_node(folder)
    store.record_sync(TARGET, {folder.id: FP_A, kept.id: FP_A, dropped.id: FP_B}, NOW)

    store.update_node(Folder(id=folder.id, name="F2", children=(kept,)))

    assert store.sync_state(TARGET) == {folder.id: FP_A, kept.id: FP_A}


def test_unknown_node_rejected(store: Store) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.record_sync(TARGET, {NodeId(Playlist(name="X").id): FP_A}, NOW)


def _state(track: Track) -> FileState:
    return FileState(
        track_id=track.id,
        size=1,
        mtime_ns=1,
        quick_hash="c" * 64,
        scanned_at=NOW,
        scanned_values={},
    )
