import dataclasses
import datetime
from pathlib import Path

import pytest

from djlib.model.cue import Cue, CueKind
from djlib.model.ids import new_track_id
from djlib.model.playlist import Playlist
from djlib.model.track import Track
from djlib.store import ConflictError, FileState, NotFoundError, Store
from djlib.store.migrations import bundled_migrations, schema_version
from djlib.store.operations import (
    AddTrack,
    MarkMissing,
    MarkPresent,
    MoveTrack,
    RefreshState,
    UpdateTrack,
)
from support.store import old_database

NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.UTC)


def state_for(track: Track, **changes: object) -> FileState:
    state = FileState(
        track_id=track.id,
        size=1234,
        mtime_ns=1_700_000_000_123_456_789,
        quick_hash="ab" * 32,
        scanned_at=NOW,
        scanned_values={"title": track.title, "year": 2017},
    )
    return dataclasses.replace(state, **changes)  # pyright: ignore[reportArgumentType]


def test_file_state_round_trip(tmp_path: Path) -> None:
    track = Track(path_origin="/music/a/x.mp3", title="X")
    with Store.open(tmp_path / "library.db") as store:
        store.apply_scan([AddTrack(track, state_for(track))])

    with Store.open(tmp_path / "library.db") as store:
        assert store.file_state(track.id) == state_for(track)
        assert store.file_states("/music/a") == {track.id: state_for(track)}
        assert store.file_states("/music/b") == {}


def test_deleted_with_the_track(store: Store) -> None:
    track = Track(path_origin="/music/x.mp3")
    store.apply_scan([AddTrack(track, state_for(track))])

    store.delete_track(track.id)

    assert store.file_state(track.id) is None


def test_list_tracks_under_root(store: Store) -> None:
    inside, sibling = Track(path_origin="/music/a/x.mp3"), Track(path_origin="/music/ab/y.mp3")
    store.add_track(inside)
    store.add_track(sibling)

    assert store.list_tracks_under("/music/a") == [inside]
    assert store.list_tracks_under("/music/a/") == [inside]


def test_version_one_database_upgrades_with_backup(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    track = Track(path_origin="/music/old.mp3", title="Old")
    old_database(path, 1, [track])

    with Store.open(path) as store:
        assert store.get_track(track.id) == track
        assert schema_version(store._db) == bundled_migrations()[-1].version  # pyright: ignore[reportPrivateUsage]
    assert len(list(tmp_path.glob("library.db.v1-*.bak"))) == 1


# Applying scan plans


def test_plan_applied(store: Store) -> None:
    moved = Track(path_origin="/music/old.mp3", cues=(Cue(kind=CueKind.HOT, start_us=5, slot=0),))
    gone = Track(path_origin="/music/gone.mp3")
    store.apply_scan([AddTrack(moved, state_for(moved)), AddTrack(gone, state_for(gone))])
    store.add_node(Playlist(name="p", entries=(moved.id, gone.id)))
    new = Track(path_origin="/music/new.mp3")
    relocated = dataclasses.replace(moved, path_origin="/music/renamed.mp3")

    store.apply_scan(
        [
            MoveTrack(relocated, state_for(relocated), old_path=moved.path),
            AddTrack(new, state_for(new)),
            MarkMissing(gone.id),
        ]
    )

    assert store.get_track(moved.id) == relocated
    assert store.get_track(moved.id).cues == moved.cues
    assert store.find_track_by_path("/music/old.mp3") is None
    assert store.get_track(new.id) == new
    gone_state = store.file_state(gone.id)
    assert gone_state is not None and gone_state.missing
    (playlist,) = store.children()
    assert playlist.entries == (moved.id, gone.id)  # pyright: ignore[reportAttributeAccessIssue]


def test_update_refresh_and_present(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="Old")
    store.apply_scan([AddTrack(track, state_for(track)), MarkMissing(track.id)])
    retitled = dataclasses.replace(track, title="New")

    store.apply_scan([MarkPresent(track.id, state_for(track, size=1))])
    store.apply_scan([UpdateTrack(retitled, state_for(retitled, size=2))])
    store.apply_scan([RefreshState(track.id, state_for(retitled, size=3))])

    assert store.get_track(track.id).title == "New"
    state = store.file_state(track.id)
    assert state is not None and (state.size, state.missing) == (3, False)


def test_stale_plan(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="T")
    store.apply_scan([AddTrack(track, state_for(track))])
    store.delete_track(track.id)
    new = Track(path_origin="/music/b.mp3")
    before = store.load_library()

    with pytest.raises(NotFoundError):
        store.apply_scan([AddTrack(new, state_for(new)), UpdateTrack(track, state_for(track))])
    assert store.load_library() == before


def test_plan_with_path_conflict_rejected(store: Store) -> None:
    existing = Track(path_origin="/music/a.mp3")
    store.apply_scan([AddTrack(existing, state_for(existing))])

    clash = Track(path_origin="/music/a.mp3")
    with pytest.raises(ConflictError):
        store.apply_scan([AddTrack(clash, state_for(clash))])


def test_missing_mark_needs_a_known_track(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.apply_scan([MarkMissing(new_track_id())])
