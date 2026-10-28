"""Building beets library databases for tests, from real beets schemas.

``legacy`` is a schema with single genre, composer and lyricist columns and absolute
paths; ``2.14`` has list fields joined with ``\\␀`` and stores paths inside the music
directory relative to it.
"""

import contextlib
import sqlite3
from collections.abc import Sequence
from pathlib import Path

FIXTURES = Path(__file__).parents[1] / "fixtures" / "beets"
SCHEMAS = {"legacy": FIXTURES / "schema-legacy.sql", "2.14": FIXTURES / "schema-2.14.sql"}
LIST_DELIMITER = "\\␀"


class BeetsDatabase:
    """A beets library under construction. Rows are written immediately."""

    def __init__(self, path: Path, *, schema: str = "legacy") -> None:
        self.path = path
        self.schema = schema
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(sqlite3.connect(path)) as db:
            db.executescript(SCHEMAS[schema].read_text(encoding="utf-8"))
        self.columns = set(self._query("SELECT name FROM pragma_table_info('items')"))

    def _query(self, sql: str, parameters: Sequence[object] = ()) -> list[object]:
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            return [row[0] for row in db.execute(sql, parameters)]

    def add_item(
        self,
        path: str | bytes,
        *,
        attributes: dict[str, str] | None = None,
        **columns: object,
    ) -> int:
        """Add an item; list values (for list columns) are joined as beets joins them."""
        values: dict[str, object] = {
            "path": path if isinstance(path, bytes) else path.encode(),
            "album_id": None,
        }
        for name, value in columns.items():
            if name not in self.columns:
                raise KeyError(f"the {self.schema} schema has no items.{name}")
            values[name] = LIST_DELIMITER.join(value) if isinstance(value, list) else value
        names = ", ".join(values)
        marks = ", ".join("?" * len(values))
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            cursor = db.execute(
                f"INSERT INTO items ({names}) VALUES ({marks})", (*values.values(),)
            )
            item_id = cursor.lastrowid
            db.executemany(
                "INSERT INTO item_attributes (entity_id, key, value) VALUES (?, ?, ?)",
                ((item_id, key, value) for key, value in (attributes or {}).items()),
            )
        assert item_id is not None
        return item_id

    def add_album(self, album: str, item_ids: Sequence[int]) -> int:
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            cursor = db.execute("INSERT INTO albums (album) VALUES (?)", (album,))
            album_id = cursor.lastrowid
            db.executemany(
                "UPDATE items SET album_id = ?, album = ? WHERE id = ?",
                ((album_id, album, item) for item in item_ids),
            )
        assert album_id is not None
        return album_id
