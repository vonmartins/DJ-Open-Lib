import sqlite3
from pathlib import Path

import pytest

from tunedex.store import database
from tunedex.store.database import APPLICATION_ID, open_database, transaction
from tunedex.store.errors import (
    BackupError,
    MigrationError,
    NotATunedexDatabaseError,
    SchemaTooNewError,
)
from tunedex.store.migrations import Migration, bundled_migrations, schema_version

M1 = Migration(
    1,
    "initial",
    f"PRAGMA application_id = {APPLICATION_ID};\n"
    "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL);",
)
M2 = Migration(2, "add_color", "ALTER TABLE items ADD COLUMN color TEXT;")


def snapshot(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir()) if p.is_file()}


def make_v1(path: Path) -> None:
    connection = open_database(path, [M1])
    connection.execute("INSERT INTO items (name) VALUES ('kept')")
    connection.close()


# Open or create


def test_new_database(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    connection = open_database(path)

    assert schema_version(connection) == bundled_migrations()[-1].version
    assert connection.execute("PRAGMA application_id").fetchone() == (APPLICATION_ID,)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    connection.close()
    assert [p.name for p in tmp_path.iterdir()] == ["library.db"]


def test_existing_database_at_current_version(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    open_database(path).close()
    before = path.read_bytes()

    open_database(path).close()

    assert [p.name for p in tmp_path.iterdir()] == ["library.db"]
    assert path.read_bytes() == before


def test_missing_parent_directory(tmp_path: Path) -> None:
    with pytest.raises(database.StoreError):
        open_database(tmp_path / "missing" / "library.db")


# Foreign files refused


def test_other_sqlite_file_refused(tmp_path: Path) -> None:
    path = tmp_path / "other.db"
    other = sqlite3.connect(path)
    other.execute("CREATE TABLE t (x)")
    other.commit()
    other.close()
    before = snapshot(tmp_path)

    with pytest.raises(NotATunedexDatabaseError):
        open_database(path)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("content", [b"just some text\n", b"", b"SQLite format 3\x00garbage"])
def test_non_database_refused(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes(content)

    with pytest.raises(NotATunedexDatabaseError):
        open_database(path)
    assert snapshot(tmp_path) == {"notes.txt": content}


def test_directory_refused(tmp_path: Path) -> None:
    with pytest.raises(NotATunedexDatabaseError):
        open_database(tmp_path)


# Newer versions refused


def test_newer_version_refused(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    connection = open_database(path)
    connection.execute("PRAGMA user_version = 99")
    connection.close()
    before = snapshot(tmp_path)

    with pytest.raises(SchemaTooNewError) as excinfo:
        open_database(path)

    latest = bundled_migrations()[-1].version
    assert (excinfo.value.found, excinfo.value.supported) == (99, latest)
    assert "99" in str(excinfo.value) and str(latest) in str(excinfo.value)
    assert snapshot(tmp_path) == before


# Versioning and backup before migrating


def test_upgrade_creates_backup_and_keeps_data(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    make_v1(path)

    connection = open_database(path, [M1, M2])

    assert schema_version(connection) == 2
    assert connection.execute("SELECT name, color FROM items").fetchall() == [("kept", None)]
    connection.close()
    backups = sorted(tmp_path.glob("library.db.v1-*.bak"))
    assert len(backups) == 1
    copy = sqlite3.connect(backups[0])
    assert schema_version(copy) == 1
    assert copy.execute("SELECT name FROM items").fetchall() == [("kept",)]
    copy.close()


def test_backup_impossible_aborts_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "library.db"
    make_v1(path)
    monkeypatch.setattr(
        database, "backup_path", lambda _path, _version: tmp_path / "missing" / "copy.bak"
    )

    with pytest.raises(BackupError):
        open_database(path, [M1, M2])

    connection = open_database(path, [M1])
    assert schema_version(connection) == 1
    connection.close()
    assert not list(tmp_path.glob("*.tmp"))


def test_backup_names_do_not_collide(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    first = database.backup_path(path, 1)
    first.write_bytes(b"")

    assert database.backup_path(path, 1) != first


def test_failed_migration_on_new_file_leaves_nothing(tmp_path: Path) -> None:
    broken = Migration(1, "broken", "CREATE TABLE ok (x);\nNOT SQL;")

    with pytest.raises(MigrationError):
        open_database(tmp_path / "library.db", [broken])
    assert list(tmp_path.iterdir()) == []


# Transactions


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    connection = open_database(tmp_path / "library.db", [M1])

    with pytest.raises(RuntimeError), transaction(connection):
        connection.execute("INSERT INTO items (name) VALUES ('lost')")
        raise RuntimeError("boom")

    assert connection.execute("SELECT count(*) FROM items").fetchone() == (0,)
    with transaction(connection):
        connection.execute("INSERT INTO items (name) VALUES ('saved')")
    assert connection.execute("SELECT name FROM items").fetchall() == [("saved",)]
    connection.close()
