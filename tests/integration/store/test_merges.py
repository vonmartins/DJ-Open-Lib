"""Merging duplicates and marking groups as not duplicates (specs/library-store)."""

import dataclasses
import datetime
from pathlib import Path

import pytest

from support.store import old_database
from tunedex.model.playlist import Playlist
from tunedex.model.track import Track
from tunedex.store import Store
from tunedex.store.errors import StoreError
from tunedex.store.migrations import bundled_migrations, schema_version
from tunedex.store.operations import (
    AddImportedTrack,
    IgnoreDuplicates,
    MergeTracks,
    RegisterSource,
)

NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)
BEETS = "beets-1a2b3c4d5e6f"


def apply(store: Store, *operations: object) -> None:
    store.apply_operations(operations, expected_revision=store.revision())  # type: ignore[arg-type]


def entries(store: Store, playlist: Playlist) -> list[object]:
    node = store.get_node(playlist.id)
    assert isinstance(node, Playlist)
    return list(node.entries)


def test_merge_applied(store: Store) -> None:
    a = Track(path_origin="/music/a.flac", title="Numb")
    b = Track(path_origin="/music/b.mp3", title="Numb", label="Tempa")
    other = Track(path_origin="/music/c.mp3", title="Other")
    store.add_track(a)
    store.add_track(other)
    apply(store, RegisterSource(BEETS, NOW), AddImportedTrack(b, BEETS, {"title": "Numb"}, "7"))
    playlist = Playlist(name="P", entries=(other.id, b.id, other.id))
    store.add_node(playlist)

    apply(store, MergeTracks(dataclasses.replace(a, label="Tempa"), (b.id,)))

    assert [t.path for t in store.list_tracks()] == ["/music/a.flac", "/music/c.mp3"]
    assert store.get_track(a.id).label == "Tempa"
    assert entries(store, playlist) == [other.id, a.id, other.id]
    assert store.merged_items(BEETS) == {"7": a.id}
    assert store.merged_paths() == {"/music/b.mp3": a.id}
    assert store.source_links(BEETS) == {}


def test_both_in_one_playlist(store: Store) -> None:
    a, b = Track(path_origin="/music/a.mp3"), Track(path_origin="/music/b.mp3")
    store.add_track(a)
    store.add_track(b)
    playlist = Playlist(name="P", entries=(b.id, a.id))
    store.add_node(playlist)

    apply(store, MergeTracks(a, (b.id,)))

    assert entries(store, playlist) == [a.id]


def test_merge_of_a_deleted_track(store: Store) -> None:
    a, b = Track(path_origin="/music/a.mp3"), Track(path_origin="/music/b.mp3")
    store.add_track(a)
    revision = store.revision()

    with pytest.raises(StoreError):
        apply(store, MergeTracks(dataclasses.replace(a, title="X"), (b.id,)))

    assert store.revision() == revision
    assert store.get_track(a.id).title is None


def test_merge_chain(store: Store) -> None:
    a, b, c = (Track(path_origin=f"/music/{n}.mp3") for n in "abc")
    for track in (a, b, c):
        store.add_track(track)

    apply(store, MergeTracks(b, (a.id,)))
    apply(store, MergeTracks(c, (b.id,)))

    assert store.merged_paths() == {"/music/a.mp3": c.id, "/music/b.mp3": c.id}


def test_records_deleted_with_the_kept_track(store: Store) -> None:
    a, b = Track(path_origin="/music/a.mp3"), Track(path_origin="/music/b.mp3")
    store.add_track(a)
    store.add_track(b)
    apply(store, MergeTracks(a, (b.id,)))

    store.delete_track(a.id)

    assert store.merged_paths() == {}


def test_marked_set_round_trip(tmp_path: Path) -> None:
    a, b = Track(path_origin="/music/a.mp3"), Track(path_origin="/music/b.mp3")
    with Store.open(tmp_path / "library.db") as store:
        store.add_track(a)
        store.add_track(b)
        apply(store, IgnoreDuplicates(frozenset({a.id, b.id})))

    with Store.open(tmp_path / "library.db") as store:
        assert store.not_duplicates() == [frozenset({a.id, b.id})]
        store.delete_track(a.id)
        assert store.not_duplicates() == [frozenset({b.id})]


def test_upgrade_from_version_six(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    track = Track(path_origin="/music/old.mp3", title="Old")
    old_database(path, 6, [track])

    with Store.open(path) as store:
        assert schema_version(store._db) == bundled_migrations()[-1].version == 7  # pyright: ignore[reportPrivateUsage]
        assert store.get_track(track.id) == track
        assert (store.merged_paths(), store.not_duplicates()) == ({}, [])
