import datetime
from pathlib import Path

from support.store import old_database
from tunedex.model.track import Track
from tunedex.store import Store
from tunedex.store.migrations import bundled_migrations, schema_version
from tunedex.store.operations import AddImportedTrack, RecordSourceValues, RegisterSource

NOW = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.UTC)
SOURCE = "beets-1a2b3c4d5e6f"


def link(store: Store, track: Track, key: str) -> None:
    store.apply_operations(
        [RegisterSource(SOURCE, NOW), AddImportedTrack(track, SOURCE, {"title": "A"}, key)],
        expected_revision=store.revision(),
    )


def test_link_round_trip(tmp_path: Path) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    with Store.open(tmp_path / "library.db") as store:
        link(store, track, "42")

    with Store.open(tmp_path / "library.db") as store:
        assert store.source_links(SOURCE) == {"42": track.id}


def test_link_kept_when_bases_change_without_a_key(tmp_path: Path) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    with Store.open(tmp_path / "library.db") as store:
        link(store, track, "42")
        store.record_sync(SOURCE, {}, NOW, source_values={track.id: {"title": "B"}})

        assert store.source_links(SOURCE) == {"42": track.id}
        assert store.source_values(SOURCE)[track.id] == {"title": "B"}


def test_key_moves_to_another_track(tmp_path: Path) -> None:
    a = Track(path_origin="/music/a.mp3", title="A")
    b = Track(path_origin="/music/b.mp3", title="B")
    with Store.open(tmp_path / "library.db") as store:
        link(store, a, "42")
        store.add_track(b)
        store.apply_operations(
            [RecordSourceValues(b.id, SOURCE, {"title": "B"}, "42")],
            expected_revision=store.revision(),
        )

        assert store.source_links(SOURCE) == {"42": b.id}


def test_link_removed_with_the_track(tmp_path: Path) -> None:
    track = Track(path_origin="/music/a.mp3", title="A")
    with Store.open(tmp_path / "library.db") as store:
        link(store, track, "42")
        store.delete_track(track.id)

        assert store.source_links(SOURCE) == {}


def test_version_five_database_upgrades_with_backup(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    track = Track(path_origin="/music/old.mp3", title="Old")
    old_database(path, 5, [track])

    with Store.open(path) as store:
        assert store.get_track(track.id) == track
        assert schema_version(store._db) == bundled_migrations()[-1].version  # pyright: ignore[reportPrivateUsage]
        assert store.source_links(SOURCE) == {}
    assert len(list(tmp_path.glob("library.db.v5-*.bak"))) == 1
