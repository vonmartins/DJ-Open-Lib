import sqlite3

import pytest

from djlib.store.errors import MigrationError
from djlib.store.migrations import (
    Migration,
    apply_migrations,
    bundled_migrations,
    schema_version,
)

V1 = Migration(1, "initial", "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL);")
V2 = Migration(2, "add_color", "ALTER TABLE items ADD COLUMN color TEXT;")
V2_FAILING = Migration(
    2,
    "broken",
    "ALTER TABLE items ADD COLUMN color TEXT;\nUPDATE items SET color = 'x';\nTHIS IS NOT SQL;",
)


def v1_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    apply_migrations(connection, [V1])
    connection.execute("INSERT INTO items (name) VALUES ('kept')")
    return connection


def columns(connection: sqlite3.Connection) -> list[str]:
    return [row[1] for row in connection.execute("PRAGMA table_info(items)")]


def test_bundled_migrations_start_at_one() -> None:
    migrations = bundled_migrations()
    assert migrations[0].version == 1
    assert migrations[0].name == "initial"


def test_new_database_reaches_latest_version() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)

    assert apply_migrations(connection, bundled_migrations()) == [1]
    assert schema_version(connection) == 1


def test_upgrade_from_older_version_preserves_data() -> None:
    connection = v1_database()

    assert apply_migrations(connection, [V1, V2]) == [2]
    assert schema_version(connection) == 2
    assert columns(connection) == ["id", "name", "color"]
    assert connection.execute("SELECT name, color FROM items").fetchall() == [("kept", None)]


def test_up_to_date_database_is_left_alone() -> None:
    connection = v1_database()
    calls: list[int] = []

    assert apply_migrations(connection, [V1], before_first=calls.append) == []
    assert calls == []


def test_failing_migration_keeps_previous_version_and_data() -> None:
    connection = v1_database()

    with pytest.raises(MigrationError) as excinfo:
        apply_migrations(connection, [V1, V2_FAILING])

    assert excinfo.value.version == 2
    assert not connection.in_transaction
    assert schema_version(connection) == 1
    assert columns(connection) == ["id", "name"]
    assert connection.execute("SELECT name FROM items").fetchall() == [("kept",)]


def test_before_first_runs_once_with_current_version() -> None:
    connection = v1_database()
    calls: list[int] = []

    apply_migrations(
        connection, [V1, V2, Migration(3, "c", "SELECT 1;")], before_first=calls.append
    )

    assert calls == [1]


def test_failing_before_first_migrates_nothing() -> None:
    connection = v1_database()

    def refuse(_version: int) -> None:
        raise OSError("disk full")

    with pytest.raises(OSError):
        apply_migrations(connection, [V1, V2], before_first=refuse)
    assert schema_version(connection) == 1


def test_gaps_rejected() -> None:
    with pytest.raises(ValueError):
        apply_migrations(sqlite3.connect(":memory:"), [V1, Migration(3, "c", "SELECT 1;")])
