import dataclasses
import datetime

import pytest

from tunedex.model.track import Track
from tunedex.store import ConflictError, FileState, NotFoundError, Store
from tunedex.store.operations import AddImportedTrack, EditTrack, RegisterSource

NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)
SOURCE = "beets-1a2b3c4d5e6f"


def edit(store: Store, track: Track) -> None:
    store.apply_operations([EditTrack(track)], expected_revision=store.revision())


def test_edited(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="Glue_Edit")
    store.apply_operations(
        [RegisterSource(SOURCE, NOW), AddImportedTrack(track, SOURCE, {"title": "x"}, "7")],
        expected_revision=store.revision(),
    )
    state = FileState(track_id=track.id, size=1, mtime_ns=1, quick_hash="0" * 64, scanned_at=NOW)
    store._put_file_state(state)  # pyright: ignore[reportPrivateUsage]
    revision = store.revision()

    edit(store, dataclasses.replace(track, title="Glue Edit"))

    assert store.get_track(track.id).title == "Glue Edit"
    assert store.file_state(track.id) == state
    assert store.source_values(SOURCE) == {track.id: {"title": "x"}}
    assert store.source_links(SOURCE) == {"7": track.id}
    assert store.revision() > revision


def test_path_cannot_change(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    store.add_track(track)

    with pytest.raises(ConflictError, match="path"):
        edit(store, dataclasses.replace(track, path_origin="/music/b.mp3", title="B"))

    assert store.get_track(track.id) == track


def test_deleted_track(store: Store) -> None:
    with pytest.raises(NotFoundError):
        edit(store, Track(path_origin="/music/a.mp3"))
