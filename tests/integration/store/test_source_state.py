import dataclasses
import datetime
import sqlite3
from pathlib import Path

import pytest

from djlib.model.playlist import Folder, Playlist
from djlib.model.track import Track
from djlib.model.unmapped import JSONValue
from djlib.store import ConflictError, NotFoundError, Store
from djlib.store.migrations import bundled_migrations, schema_version
from djlib.store.operations import (
    AddImportedTrack,
    LibraryOperation,
    RecordSourceValues,
    RegisterSource,
    ReplaceSourceFolder,
    UpdateImportedTrack,
)
from support.store import old_database

NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.UTC)
SOURCE = "mixxx-1a2b3c4d5e6f"


def imported(track: Track, folder: Folder, **values: JSONValue) -> list[LibraryOperation]:
    return [
        AddImportedTrack(track, SOURCE, {"title": track.title, **values}),
        ReplaceSourceFolder(SOURCE, folder),
        RegisterSource(SOURCE, NOW),  # applied first wherever it is
    ]


def test_source_state_round_trip(tmp_path: Path) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    folder = Folder(name="Mixxx", children=(Playlist(name="P", entries=(track.id,)),))
    with Store.open(tmp_path / "library.db") as store:
        store.apply_operations(imported(track, folder, bpm=127.0))

    with Store.open(tmp_path / "library.db") as store:
        info = store.source(SOURCE)
        assert info is not None
        assert (info.root_node_id, info.imported_at) == (folder.id, NOW)
        assert store.source_values(SOURCE) == {track.id: {"title": "A", "bpm": 127.0}}
        assert store.get_node(folder.id) == folder
        assert store.source("mixxx-000000000000") is None


def test_source_folder_deleted(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    folder = Folder(name="Mixxx")
    store.apply_operations(imported(track, folder))

    store.delete_node(folder.id)

    info = store.source(SOURCE)
    assert info is not None and info.root_node_id is None
    assert store.source_values(SOURCE) == {track.id: {"title": "A"}}


def test_folder_recreated_after_deletion(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    store.apply_operations(imported(track, Folder(name="Mixxx")))
    store.delete_node(store.children()[0].id)
    again = Folder(name="Mixxx")

    store.apply_operations([RegisterSource(SOURCE, NOW), ReplaceSourceFolder(SOURCE, again)])

    info = store.source(SOURCE)
    assert info is not None and info.root_node_id == again.id


def test_import_applied(store: Store) -> None:
    old = Track(path_origin="/music/old.mp3", title="Old")
    store.add_track(old)
    store.add_node(Playlist(name="Mine"))
    new = Track(path_origin="/music/new.mp3", title="New")
    folder = Folder(name="Mixxx", children=(Playlist(name="P", entries=(new.id, old.id)),))
    revision = store.revision()

    store.apply_operations(
        [
            RegisterSource(SOURCE, NOW),
            AddImportedTrack(new, SOURCE, {"title": "New"}),
            UpdateImportedTrack(dataclasses.replace(old, bpm=128.0), SOURCE, {"bpm": 128.0}),
            ReplaceSourceFolder(SOURCE, folder),
        ],
        expected_revision=revision,
    )

    assert store.get_track(old.id).bpm == 128.0
    assert store.find_track_by_path(new.path) == new
    assert [n.name for n in store.children()] == ["Mine", "Mixxx"]
    assert store.source_values(SOURCE) == {new.id: {"title": "New"}, old.id: {"bpm": 128.0}}
    assert store.revision() > revision


def test_replacing_keeps_ids_and_sync_state(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    peak = Playlist(name="Peak")
    folder = Folder(name="Mixxx", children=(Folder(name="Playlists", children=(peak,)),))
    store.apply_operations(imported(track, folder))
    store.record_sync("m3u-aaaaaaaaaaaa", {peak.id: "f" * 64}, NOW)

    grown = dataclasses.replace(peak, entries=(track.id,))
    replaced = Folder(
        id=folder.id,
        name="Mixxx",
        children=(Folder(id=folder.children[0].id, name="Playlists", children=(grown,)),),
    )
    store.apply_operations([RegisterSource(SOURCE, NOW), ReplaceSourceFolder(SOURCE, replaced)])

    assert store.get_node(peak.id) == grown
    assert store.sync_state("m3u-aaaaaaaaaaaa") == {peak.id: "f" * 64}
    info = store.source(SOURCE)
    assert info is not None and info.root_node_id == folder.id


def test_folder_with_another_id_refused(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    store.apply_operations(imported(track, Folder(name="Mixxx")))

    with pytest.raises(ConflictError):
        store.apply_operations(
            [RegisterSource(SOURCE, NOW), ReplaceSourceFolder(SOURCE, Folder(name="Mixxx"))]
        )


def test_stale_import(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    store.add_track(track)
    store.delete_track(track.id)
    revision, before = store.revision(), store.load_library()

    with pytest.raises(NotFoundError):
        store.apply_operations(
            [RegisterSource(SOURCE, NOW), UpdateImportedTrack(track, SOURCE, {})]
        )
    with pytest.raises(NotFoundError):
        store.apply_operations(
            [RegisterSource(SOURCE, NOW), RecordSourceValues(track.id, SOURCE, {})]
        )

    assert (store.revision(), store.load_library(), store.source(SOURCE)) == (
        revision,
        before,
        None,
    )


def test_values_need_a_registered_source(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        store.apply_operations([AddImportedTrack(track, SOURCE, {})])


def test_values_deleted_with_the_track(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    store.apply_operations(imported(track, Folder(name="Mixxx")))

    store.delete_track(track.id)

    assert store.source_values(SOURCE) == {}


def test_version_three_database_upgrades_with_backup(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    track = Track(path_origin="/music/old.mp3", title="Old")
    old_database(path, 3, [track])

    with Store.open(path) as store:
        assert store.get_track(track.id) == track
        assert schema_version(store._db) == bundled_migrations()[-1].version  # pyright: ignore[reportPrivateUsage]
        assert store.source(SOURCE) is None
    assert len(list(tmp_path.glob("library.db.v3-*.bak"))) == 1


def test_sources_listed(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    other = Track(path_origin="/music/b.mp3", title="B")
    store.add_track(other)
    store.apply_operations(imported(track, Folder(name="Mixxx")))

    assert [(s.name, s.imported_at) for s in store.sources()] == [(SOURCE, NOW)]
    assert store.sources_of(track.id) == [SOURCE]
    assert store.sources_of(other.id) == []
