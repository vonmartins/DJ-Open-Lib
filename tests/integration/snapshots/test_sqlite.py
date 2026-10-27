import sqlite3
from pathlib import Path

from djlib.model.track import Track
from djlib.snapshots import SnapshotStore
from djlib.store import Store
from support.files import sha256


def test_open_library_database(snapshots: SnapshotStore, app_dir: Path) -> None:
    database = app_dir / "library.db"
    with Store.open(database) as store:
        store.add_track(Track(path_origin="/music/committed.mp3"))
        connection = store._db  # pyright: ignore[reportPrivateUsage]
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO tracks (id, path, path_origin) VALUES ('x', '/music/pending.mp3', '/p')"
        )

        snapshot = snapshots.create("library", [database])

        connection.execute("ROLLBACK")

    (record,) = snapshot.files
    assert record.method == "sqlite"
    copy = snapshots.root / "library" / snapshot.id / "files" / "0"
    assert sha256(copy) == record.sha256
    reader = sqlite3.connect(f"{copy.resolve().as_uri()}?mode=ro", uri=True)
    assert reader.execute("SELECT path FROM tracks").fetchall() == [("/music/committed.mp3",)]
    reader.close()


def test_damaged_database_is_copied_raw(snapshots: SnapshotStore, app_dir: Path) -> None:
    damaged = app_dir / "library.db"
    damaged.write_bytes(b"SQLite format 3\x00" + b"\xff" * 200)

    snapshot = snapshots.create("library", [damaged])

    (record,) = snapshot.files
    assert record.method == "copy"
    assert record.sha256 == sha256(damaged)
