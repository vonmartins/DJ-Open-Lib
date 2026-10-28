"""Reading a beets library database into canonical tracks.

The database is opened read-only and copied to memory first, so reading never creates
or changes a file. Columns are discovered at runtime: older libraries have single
``genre``, ``composer`` and ``lyricist`` columns, beets 2.14 and later have lists
(``genres``…) and store paths inside the music directory relative to it.
"""

import datetime
import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from djlib.adapters.errors import AdapterReadError
from djlib.adapters.pathmap import PathMapping
from djlib.model.errors import ValidationError
from djlib.model.key import parse_musical, parse_open_key
from djlib.model.track import Track
from djlib.model.unmapped import JSONValue
from djlib.sources.tags import format_of_extension

NAME = "beets"
DATABASE = "library.db"
LIST_DELIMITER = "\\␀"
_SQLITE_HEADER = b"SQLite format 3\x00"

# beets column -> Track field, for text values. A list column (``genres``) wins over
# the single column (``genre``) of older schemas when both exist.
_TEXT = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "albumartist": "album_artist",
    "grouping": "grouping",
    "comments": "comment",
    "label": "label",
}
_LISTS = {
    "genre": ("genres", "genre"),
    "composer": ("composers", "composer"),
    "lyricist": ("lyricists", "lyricist"),
    "remixer": ("remixers", "remixer"),
}
_INTEGERS = {"year": "year", "track": "track_number", "disc": "disc_number"}
# Kept under unmapped["beets"] when set.
_UNMAPPED = (
    "mb_trackid",
    "mb_albumid",
    "mb_artistid",
    "mb_albumartistid",
    "mb_releasetrackid",
    "mb_releasegroupid",
    "mb_workid",
    "discogs_albumid",
    "discogs_artistid",
    "discogs_labelid",
    "isrc",
    "catalognum",
    "style",
    "country",
    "media",
    "albumtype",
    "original_year",
    "original_month",
    "original_day",
    "artist_sort",
    "albumartist_sort",
    "rg_track_gain",
    "rg_track_peak",
    "rg_album_gain",
    "rg_album_peak",
    "r128_track_gain",
    "r128_album_gain",
    "acoustid_id",
)


def database_path(location: Path) -> Path:
    """The database file for a file or a directory holding ``library.db``."""
    return location / DATABASE if location.is_dir() else location


def _open_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def not_beets(location: Path) -> str | None:
    """Why ``location`` is not a beets library, or ``None`` when it is one."""
    path = database_path(location)
    try:
        with path.open("rb") as file:
            if file.read(len(_SQLITE_HEADER)) != _SQLITE_HEADER:
                return f"{path} is not an SQLite database"
    except OSError:
        return f"{path} does not exist"
    try:
        db = _open_read_only(path)
    except sqlite3.Error as error:
        return str(error)
    try:
        tables = {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "items" not in tables:
            return "no beets items table in the database"
        if "item_attributes" not in tables:
            return "no beets item_attributes table in the database"
        columns = {row[1] for row in db.execute("PRAGMA table_info(items)")}
    except sqlite3.Error as error:
        return str(error)
    finally:
        db.close()
    return None if "path" in columns else "the items table has no path column"


def snapshot(path: Path) -> sqlite3.Connection:
    """An in-memory copy of the database at ``path``, taken in one read transaction."""
    try:
        source = _open_read_only(path)
    except sqlite3.Error as error:
        raise AdapterReadError(path, str(error)) from error
    memory = sqlite3.connect(":memory:")
    try:
        source.backup(memory)
    except sqlite3.Error as error:
        memory.close()
        raise AdapterReadError(path, str(error)) from error
    finally:
        source.close()
    return memory


@dataclass
class BeetsReader:
    path_mapping: PathMapping = field(default_factory=PathMapping)
    music_dir: Path | None = None
    warnings: list[str] = field(default_factory=list[str])
    _skipped: Counter[str] = field(default_factory=Counter[str])

    def read(self, location: Path) -> list[Track]:
        path = database_path(location)
        reason = not_beets(path)
        if reason is not None:
            raise AdapterReadError(path, reason)
        db = snapshot(path)
        db.row_factory = sqlite3.Row
        try:
            return self._tracks(db, path)
        finally:
            db.close()

    def _tracks(self, db: sqlite3.Connection, path: Path) -> list[Track]:
        columns = {row[1] for row in db.execute("PRAGMA table_info(items)")}
        attributes: defaultdict[int, dict[str, JSONValue]] = defaultdict(dict)
        for entity_id, key, value in db.execute(
            "SELECT entity_id, key, value FROM item_attributes ORDER BY entity_id, key"
        ):
            attributes[entity_id][key] = value
        rows = db.execute("SELECT * FROM items ORDER BY id").fetchall()
        if self.music_dir is None and any(_is_relative(_path_bytes(r["path"])) for r in rows):
            raise AdapterReadError(
                path,
                "the library stores paths relative to beets' music directory; give it"
                " with --music-dir, or set `directory` in beets' config.yaml",
            )
        tracks: list[Track] = []
        for row in rows:
            track = self._track(row, columns, attributes.get(row["id"], {}))
            if track is not None:
                tracks.append(track)
        for reason, count in self._skipped.items():
            self.warnings.append(f"{count} {reason} were skipped")
        return tracks

    def _path(self, stored: object) -> str | None:
        raw = _path_bytes(stored)
        if not raw:
            return None
        text = raw.decode("utf-8", "surrogateescape")
        if _is_relative(raw) and self.music_dir is not None:  # checked before reading
            # beets stores relative paths with "/"; join lexically, normalization follows.
            text = os.fspath(self.music_dir).rstrip("/\\") + "/" + text
        return text

    def _track(
        self, row: sqlite3.Row, columns: set[str], attributes: dict[str, JSONValue]
    ) -> Track | None:
        stored = self._path(row["path"])
        if stored is None:
            self._skipped["items without a path"] += 1
            return None
        values: dict[str, Any] = {}
        for column, name in _TEXT.items():
            if column in columns:
                values[name] = _text(row[column])
        for name, (plural, single) in _LISTS.items():
            if plural in columns:
                values[name] = _joined(row[plural])
            elif single in columns:
                values[name] = _text(row[single])
        for column, name in _INTEGERS.items():
            if column in columns:
                values[name] = _positive_int(row[column])
        if "bpm" in columns:
            bpm = row["bpm"]
            values["bpm"] = float(bpm) if isinstance(bpm, int | float) and bpm > 0 else None
        if "initial_key" in columns:
            key_text = _text(row["initial_key"])
            values["key_original"] = key_text
            values["key"] = None if key_text is None else (
                parse_open_key(key_text) or parse_musical(key_text)
            )  # fmt: skip
        if "length" in columns:
            length = row["length"]
            values["duration_us"] = (
                round(length * 1_000_000)
                if isinstance(length, int | float) and length > 0
                else None
            )
        if "bitrate" in columns:
            bitrate = row["bitrate"]
            values["bitrate"] = (
                round(bitrate / 1000) if isinstance(bitrate, int | float) and bitrate > 0 else None
            )
        if "samplerate" in columns:
            values["sample_rate"] = _positive_int(row["samplerate"])
        if "added" in columns:
            values["date_added"] = _date(row["added"])
        values["release_date"] = _release_date(row, columns)
        values["file_format"] = format_of_extension(stored)

        unmapped: dict[str, JSONValue] = {"id": row["id"]}
        for column in _UNMAPPED:
            if column in columns and (value := row[column]) not in (None, "", 0):
                unmapped[column] = value
        if attributes:
            unmapped["attributes"] = attributes
        try:
            location = self.path_mapping.to_library(stored)
            return _build(location, values, unmapped, stored, self.warnings)
        except ValidationError as error:
            self.warnings.append(f"skipped beets item {stored!r}: {error.message}")
            return None


def _build(
    location: str,
    values: dict[str, Any],
    unmapped: dict[str, JSONValue],
    stored: str,
    warnings: list[str],
) -> Track:
    """Build a track, dropping (with a warning) any value the model rejects."""
    values = {k: v for k, v in values.items() if v is not None}
    while True:
        try:
            return Track(path_origin=location, unmapped={NAME: unmapped}, **values)
        except ValidationError as error:
            if error.field not in values:
                raise
            warnings.append(f"{stored}: ignored invalid {error.field} ({error.message})")
            del values[error.field]


def _path_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):  # a path set by hand as TEXT
        return value.encode("utf-8", "surrogateescape")
    return b""


def _is_relative(raw: bytes) -> bool:
    if not raw:
        return False
    text = raw.decode("utf-8", "surrogateescape")
    return not (text.startswith("/") or _is_windows_absolute(text))


def _is_windows_absolute(text: str) -> bool:
    """``C:\\…``, ``C:/…`` or ``\\\\server\\…``, as beets stores absolute Windows paths."""
    return (len(text) > 2 and text[1] == ":" and text[2] in "\\/") or text.startswith("\\\\")


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _joined(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parts = [part.strip() for part in value.split(LIST_DELIMITER)]
    return ", ".join(part for part in parts if part) or None


def _positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _date(value: object) -> datetime.date | None:
    if not isinstance(value, int | float) or value <= 0:
        return None
    return datetime.datetime.fromtimestamp(value, datetime.UTC).date()


def _release_date(row: sqlite3.Row, columns: set[str]) -> datetime.date | None:
    if not {"year", "month", "day"} <= columns:
        return None
    year, month, day = row["year"], row["month"], row["day"]
    if not all(isinstance(v, int) and v > 0 for v in (year, month, day)):
        return None
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None
