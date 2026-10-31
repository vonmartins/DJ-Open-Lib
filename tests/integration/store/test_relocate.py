import dataclasses
import datetime

import pytest

from tunedex.model.cue import Cue, CueKind
from tunedex.model.track import Track
from tunedex.store import ConflictError, FileState, NotFoundError, Store
from tunedex.store.operations import AddImportedTrack, RegisterSource, RelocateTrack

NOW = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.UTC)
SOURCE = "beets-1a2b3c4d5e6f"


def relocate(store: Store, track: Track, path: str) -> None:
    store.apply_operations([RelocateTrack(track.id, path)], expected_revision=store.revision())


def test_relocated(store: Store) -> None:
    cue = Cue(kind=CueKind.HOT, start_us=1_000_000, slot=0)
    track = Track(path_origin="/mnt/Elements/a.mp3", title="A", cues=(cue,))
    store.apply_operations(
        [RegisterSource(SOURCE, NOW), AddImportedTrack(track, SOURCE, {"title": "A"}, "42")],
        expected_revision=store.revision(),
    )
    revision = store.revision()

    relocate(store, track, "/home/me/Elements/a.mp3")

    moved = store.get_track(track.id)
    assert moved == dataclasses.replace(track, path_origin="/home/me/Elements/a.mp3")
    assert store.source_values(SOURCE) == {track.id: {"title": "A"}}
    assert store.source_links(SOURCE) == {"42": track.id}
    assert store.revision() > revision
    assert store.file_state(track.id) is None


def test_file_state_marked_present(store: Store) -> None:
    track = Track(path_origin="/old/a.mp3", title="A")
    store.add_track(track)
    state = FileState(
        track_id=track.id, size=10, mtime_ns=1, quick_hash="0" * 64, scanned_at=NOW, missing=True
    )
    store.apply_operations(
        [RelocateTrack(track.id, "/new/a.mp3")], expected_revision=store.revision()
    )  # no state yet: nothing to mark
    store._put_file_state(state)  # pyright: ignore[reportPrivateUsage]

    relocate(store, track, "/newer/a.mp3")

    assert store.file_state(track.id) == dataclasses.replace(state, missing=False)


def test_path_taken(store: Store) -> None:
    a, b = Track(path_origin="/music/a.mp3"), Track(path_origin="/old/b.mp3")
    store.add_track(a)
    store.add_track(b)
    revision = store.revision()

    with pytest.raises(ConflictError):
        relocate(store, b, "/music/a.mp3")

    assert store.get_track(b.id).path == "/old/b.mp3" and store.revision() == revision


def test_deleted_track(store: Store) -> None:
    track = Track(path_origin="/old/a.mp3")

    with pytest.raises(NotFoundError):
        relocate(store, track, "/new/a.mp3")
