"""The enrichment cache: fingerprints and service answers, in ``<home>/cache.db``.

It is separate from the library, so snapshots and plans never include it, and it can be
deleted at any time. With ``refresh``, cached answers are ignored but still updated.
"""

import contextlib
import json
import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fingerprints (
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    duration REAL NOT NULL,
    fingerprint TEXT NOT NULL,
    PRIMARY KEY (path)
);
CREATE TABLE IF NOT EXISTS responses (
    key TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Cache:
    def __init__(self, path: Path | None, *, refresh: bool = False) -> None:
        """``path`` ``None`` keeps everything in memory (nothing is written to disk)."""
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(":memory:" if path is None else path)
        self._db.executescript(_SCHEMA)
        self.refresh = refresh

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def fingerprint(self, path: str, size: int, mtime_ns: int) -> tuple[float, str] | None:
        row = self._db.execute(
            "SELECT duration, fingerprint FROM fingerprints"
            " WHERE path = ? AND size = ? AND mtime_ns = ?",
            (path, size, mtime_ns),
        ).fetchone()
        return None if row is None else (row[0], row[1])

    def put_fingerprint(
        self, path: str, size: int, mtime_ns: int, duration: float, fingerprint: str
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO fingerprints VALUES (?, ?, ?, ?, ?)",
                (path, size, mtime_ns, duration, fingerprint),
            )

    def response(self, key: str) -> Any:
        if self.refresh:
            return None
        row = self._db.execute("SELECT body FROM responses WHERE key = ?", (key,)).fetchone()
        return None if row is None else json.loads(row[0])

    def put_response(self, key: str, value: Any) -> None:
        with self._db, contextlib.suppress(sqlite3.Error):
            self._db.execute(
                "INSERT OR REPLACE INTO responses (key, body) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )
