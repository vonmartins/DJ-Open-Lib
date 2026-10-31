import re
import sqlite3
from importlib.resources import files

SCHEMA = files("tunedex.store") / "schema" / "0001_initial.sql"


def apply_schema() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    return connection


def test_initial_schema_applies() -> None:
    connection = apply_schema()
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }

    assert tables == {
        "tracks",
        "cues",
        "beat_markers",
        "tags",
        "track_tags",
        "playlist_nodes",
        "playlist_entries",
        "smartlist_rules",
    }
    assert connection.execute("PRAGMA application_id").fetchone() == (0x544E4458,)


def test_every_table_is_commented() -> None:
    sql = SCHEMA.read_text(encoding="utf-8")
    tables = [
        row[0]
        for row in apply_schema().execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    ]

    for table in tables:
        assert re.search(rf"-- Table: {table}\.[^\n]*\n(--[^\n]*\n)*CREATE TABLE {table} ", sql), (
            table
        )


def test_check_constraints_reject_bad_rows() -> None:
    connection = apply_schema()
    bad_rows = [
        "INSERT INTO tracks (id, path, path_origin, rating) VALUES ('a', '/a', '/a', 6)",
        "INSERT INTO tracks (id, path, path_origin, color) VALUES ('a', '/a', '/a', 'red')",
        "INSERT INTO tracks (id, path, path_origin, unmapped) VALUES ('a', '/a', '/a', '{bad')",
        "INSERT INTO tracks (id, path, path_origin, year) VALUES ('a', '/a', '/a', 'soon')",
    ]
    for statement in bad_rows:
        try:
            connection.execute(statement)
        except sqlite3.IntegrityError:
            continue
        raise AssertionError(f"accepted: {statement}")
