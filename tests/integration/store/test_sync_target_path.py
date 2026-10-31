import datetime
from pathlib import Path

from support.store import old_database
from tunedex.model.playlist import Folder, Playlist
from tunedex.model.track import Track
from tunedex.store import Store
from tunedex.store.migrations import bundled_migrations, schema_version
from tunedex.store.operations import RegisterSource, ReplaceSourceFolder

NOW = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.UTC)
TARGET = "mixxx-1a2b3c4d5e6f"


def test_target_path_recorded(tmp_path: Path) -> None:
    peak = Playlist(name="Peak")
    with Store.open(tmp_path / "library.db") as store:
        store.add_node(Folder(name="Techno", children=(peak,)))
        store.record_sync(
            TARGET, {peak.id: "0" * 64}, NOW, target_paths={peak.id: ("Playlists", "Techno / Peak")}
        )

    with Store.open(tmp_path / "library.db") as store:
        assert store.sync_paths(TARGET) == {peak.id: ("Playlists", "Techno / Peak")}
        assert store.sync_state(TARGET) == {peak.id: "0" * 64}


def test_target_path_kept_when_a_parent_is_replaced(tmp_path: Path) -> None:
    peak = Playlist(name="Peak")
    techno = Folder(name="Techno", children=(peak,))
    with Store.open(tmp_path / "library.db") as store:
        store.add_node(techno)
        store.record_sync(TARGET, {peak.id: "0" * 64}, NOW, target_paths={peak.id: ("P",)})
        store.update_node(Folder(id=techno.id, name="Techno 2", children=(peak,)))

        assert store.sync_paths(TARGET) == {peak.id: ("P",)}


def test_bases_recorded_with_the_sync_state(tmp_path: Path) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    with Store.open(tmp_path / "library.db") as store:
        store.add_track(track)
        store.record_sync(TARGET, {}, NOW, source_values={track.id: {"title": "A"}})

        info = store.source(TARGET)
        assert info is not None and info.root_node_id is None
        assert store.source_values(TARGET) == {track.id: {"title": "A"}}


def test_existing_source_keeps_its_folder(tmp_path: Path) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    folder = Folder(name="Mixxx")
    with Store.open(tmp_path / "library.db") as store:
        store.add_track(track)
        store.apply_operations(
            [RegisterSource(TARGET, NOW), ReplaceSourceFolder(TARGET, folder)],
            expected_revision=store.revision(),
        )
        store.record_sync(TARGET, {}, NOW, source_values={track.id: {"title": "B"}})

        info = store.source(TARGET)
        assert info is not None and info.root_node_id == folder.id


def test_version_four_database_upgrades_with_backup(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    track = Track(path_origin="/music/old.mp3", title="Old")
    old_database(path, 4, [track])

    with Store.open(path) as store:
        assert store.get_track(track.id) == track
        assert schema_version(store._db) == bundled_migrations()[-1].version  # pyright: ignore[reportPrivateUsage]
        assert store.sync_paths(TARGET) == {}
    assert len(list(tmp_path.glob("library.db.v4-*.bak"))) == 1
