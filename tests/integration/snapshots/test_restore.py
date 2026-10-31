from pathlib import Path

from support.files import sha256
from tunedex.model.track import Track
from tunedex.snapshots import SnapshotStore
from tunedex.store import Store

NML = "".join(
    f'<ENTRY TITLE="Track {i}"><LOCATION FILE="{i}.mp3"/><CUE_V2 START="{i}.5"/></ENTRY>\n'
    for i in range(200)
)


def test_corrupted_target_restored(snapshots: SnapshotStore, app_dir: Path) -> None:
    collection = app_dir / "collection.nml"
    collection.write_text(NML, encoding="utf-8")
    original_hash = sha256(collection)
    snapshot = snapshots.create("traktor", [collection])

    with collection.open("r+b") as file:
        file.seek(100)
        file.write(b"\x00garbage\x00")
        file.truncate(500)
    assert sha256(collection) != original_hash

    result = snapshots.restore(snapshot)

    assert sha256(collection) == original_hash == snapshot.files[0].sha256
    assert result.restored == snapshot
    assert result.pre_restore.reason == "pre-restore"
    assert not [p for p in app_dir.iterdir() if p.name.endswith(".tmp")]


def test_restore_removes_file_created_after_snapshot(
    snapshots: SnapshotStore, app_dir: Path
) -> None:
    existing, new = app_dir / "a.m3u", app_dir / "new.m3u"
    existing.write_text("a", encoding="utf-8")
    snapshot = snapshots.create("m3u", [existing, new])
    new.write_text("created by an export", encoding="utf-8")
    existing.write_text("changed", encoding="utf-8")

    snapshots.restore(snapshot)

    assert not new.exists()
    assert existing.read_text(encoding="utf-8") == "a"


def test_undo_a_restore(snapshots: SnapshotStore, app_dir: Path) -> None:
    collection = app_dir / "collection.nml"
    collection.write_text("A", encoding="utf-8")
    snapshot_a = snapshots.create("traktor", [collection])
    collection.write_text("B", encoding="utf-8")

    result = snapshots.restore(snapshot_a)
    assert collection.read_text(encoding="utf-8") == "A"

    snapshots.restore(result.pre_restore)
    assert collection.read_text(encoding="utf-8") == "B"


def test_missing_parent_directory_recreated(snapshots: SnapshotStore, app_dir: Path) -> None:
    nested = app_dir / "Traktor 4" / "collection.nml"
    nested.parent.mkdir()
    nested.write_text("A", encoding="utf-8")
    snapshot = snapshots.create("traktor", [nested])
    nested.unlink()
    nested.parent.rmdir()

    snapshots.restore(snapshot)

    assert nested.read_text(encoding="utf-8") == "A"


def test_library_database_restored(snapshots: SnapshotStore, app_dir: Path) -> None:
    database = app_dir / "library.db"
    kept = Track(path_origin="/music/kept.mp3")
    with Store.open(database) as store:
        store.add_track(kept)
    snapshot = snapshots.create("library", [database])
    with Store.open(database) as store:
        store.delete_track(kept.id)
        store.add_track(Track(path_origin="/music/later.mp3"))

    snapshots.restore(snapshot)

    with Store.open(database) as store:
        assert store.list_tracks() == [kept]
