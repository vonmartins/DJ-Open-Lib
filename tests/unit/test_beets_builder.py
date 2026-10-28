import contextlib
import sqlite3
from pathlib import Path

import pytest

from support.beets import BeetsDatabase


@pytest.mark.parametrize("schema", ["legacy", "2.14"])
def test_builder_uses_the_real_schema(tmp_path: Path, schema: str) -> None:
    database = BeetsDatabase(tmp_path / "library.db", schema=schema)
    item = database.add_item("/music/a.mp3", title="A")
    database.set_attributes(item, {"data_source": "MusicBrainz"})

    with contextlib.closing(sqlite3.connect(database.path)) as db:
        assert db.execute("SELECT path, title FROM items").fetchall() == [(b"/music/a.mp3", "A")]
        assert db.execute("SELECT entity_id, key FROM item_attributes").fetchall() == [
            (item, "data_source")
        ]
    assert ("genres" in database.columns) is (schema == "2.14")
    assert ("genre" in database.columns) is (schema == "legacy")


def test_lists_joined_as_beets_joins_them(tmp_path: Path) -> None:
    database = BeetsDatabase(tmp_path / "library.db", schema="2.14")
    database.add_item("a.mp3", genres=["Techno", "Minimal"])

    with contextlib.closing(sqlite3.connect(database.path)) as db:
        assert db.execute("SELECT genres FROM items").fetchone() == ("Techno\\␀Minimal",)
