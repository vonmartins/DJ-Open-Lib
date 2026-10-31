"""Reading a Mixxx library database (schema 39, Mixxx 2.5) into the canonical model.

The database is opened read-only and copied to memory first: reading sees one
consistent state even while Mixxx runs, and never creates or changes a file.
"""

import base64
import datetime
import re
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tunedex.adapters.errors import AdapterReadError
from tunedex.adapters.mixxx.beats import ProtobufError, grid_from_mixxx
from tunedex.adapters.mixxx.keys import key_from_id
from tunedex.adapters.pathmap import PathMapping
from tunedex.model.beatgrid import BeatGrid
from tunedex.model.cue import Cue, CueKind
from tunedex.model.errors import ValidationError
from tunedex.model.ids import TrackId
from tunedex.model.library import Library
from tunedex.model.playlist import Folder, Node, Playlist
from tunedex.model.track import Track
from tunedex.model.unmapped import JSONValue

NAME = "mixxx"
DATABASE = "mixxxdb.sqlite"
SUPPORTED_SCHEMA = 39
# The name given to Mixxx's unlabelled main cue; written back as no label.
MAIN_CUE_NAME = "Main cue"
_SQLITE_HEADER = b"SQLite format 3\x00"
_SCHEMA_KEY = "mixxx.schema.version"

# cues.type values.
_HOT_CUE, _MAIN_CUE, _LOOP, _INTRO, _OUTRO = 1, 2, 4, 6, 7
# Playlists.hidden values.
_AUTO_DJ, _HISTORY = 1, 2

_LEADING_NUMBER = re.compile(r"^\s*(\d+)")
_YEAR = re.compile(r"^\s*(\d{4})")
_TEXT_COLUMNS = (
    "artist",
    "title",
    "album",
    "album_artist",
    "genre",
    "composer",
    "grouping",
    "comment",
)


def database_path(location: Path) -> Path:
    """The database file for a file or a Mixxx settings directory."""
    return location / DATABASE if location.is_dir() else location


def schema_version(location: Path) -> int | None:
    """Mixxx's schema version, or ``None`` when ``location`` is not a Mixxx database."""
    path = database_path(location)
    try:
        with path.open("rb") as file:
            if file.read(len(_SQLITE_HEADER)) != _SQLITE_HEADER:
                return None
    except OSError:
        return None
    try:
        connection = _open_read_only(path)
    except sqlite3.Error:
        return None
    try:
        row = connection.execute(
            "SELECT value FROM settings WHERE name = ?", (_SCHEMA_KEY,)
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    try:
        return None if row is None else int(row[0])
    except ValueError:
        return None


def _open_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


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
        hint = (
            "; if Mixxx closed unexpectedly, start and quit it once, then try again"
            if "locked" in str(error) or "journal" in str(error)
            else ""
        )
        raise AdapterReadError(path, f"{error}{hint}") from error
    finally:
        source.close()
    return memory


@dataclass
class MixxxReader:
    path_mapping: PathMapping = field(default_factory=PathMapping)
    warnings: list[str] = field(default_factory=list[str])
    keys: dict[TrackId, str] = field(default_factory=dict[TrackId, str])
    """The Mixxx ``library.id`` of each track of the last read."""
    _skipped: Counter[str] = field(default_factory=Counter[str])

    def read(self, location: Path) -> Library:
        path = database_path(location)
        version = schema_version(path)
        if version is None:
            raise AdapterReadError(path, "not a Mixxx library database")
        if version < SUPPORTED_SCHEMA:
            raise AdapterReadError(
                path,
                f"Mixxx schema version {version} is too old; version {SUPPORTED_SCHEMA}"
                " (Mixxx 2.5) is supported. Open the library once in Mixxx 2.5 to upgrade it",
            )
        if version > SUPPORTED_SCHEMA:
            self.warnings.append(
                f"Mixxx schema version {version} is newer than the tested version"
                f" {SUPPORTED_SCHEMA}; some data may be missed"
            )
        db = snapshot(path)
        try:
            return self.read_database(db)
        finally:
            db.close()

    def read_database(self, db: sqlite3.Connection) -> Library:
        """Read an open Mixxx database (already checked to be a supported version)."""
        tracks, playlists = self.read_rows(db)
        self.keys = {track.id: str(mixxx_id) for mixxx_id, track in tracks.items()}
        return Library.build(tracks.values(), playlists)

    def read_rows(self, db: sqlite3.Connection) -> tuple[dict[int, Track], tuple[Node, ...]]:
        """The tracks by their Mixxx id, and the ``Playlists`` and ``Crates`` folders."""
        factory = db.row_factory
        db.row_factory = sqlite3.Row
        try:
            tracks = self._tracks(db)
            playlists = self._playlists(db, tracks)
        finally:
            db.row_factory = factory
        self._report_skipped()
        return tracks, playlists

    # Tracks

    def _tracks(self, db: sqlite3.Connection) -> dict[int, Track]:
        cues = self._cue_rows(db)
        tracks: dict[int, Track] = {}
        missing = 0
        for row in db.execute(
            "SELECT library.*, track_locations.location AS path,"
            " track_locations.fs_deleted AS fs_deleted"
            " FROM library JOIN track_locations ON library.location = track_locations.id"
            " WHERE coalesce(library.mixxx_deleted, 0) = 0 ORDER BY track_locations.location"
        ):
            track = self._track(row, cues.get(row["id"], []))
            if track is not None:
                tracks[row["id"]] = track
                missing += bool(row["fs_deleted"])
        if missing:
            self.warnings.append(f"{missing} tracks have files that Mixxx reports as missing")
        return tracks

    def _track(self, row: sqlite3.Row, cue_rows: list[sqlite3.Row]) -> Track | None:
        path: str = row["path"]
        sample_rate = _positive_int(row["samplerate"])
        unmapped: dict[str, JSONValue] = {"id": row["id"]}
        for column in ("replaygain", "replaygain_peak"):
            if row[column] is not None:
                unmapped[column] = row[column]
        unmapped["bpm_lock"] = bool(row["bpm_lock"])
        if row["tracktotal"] not in (None, "", "//"):
            unmapped["tracktotal"] = row["tracktotal"]

        values: dict[str, Any] = {name: _text(row[name]) for name in _TEXT_COLUMNS}
        values |= {
            "year": _match_int(_YEAR, row["year"]),
            "track_number": _match_int(_LEADING_NUMBER, row["tracknumber"]),
            "duration_us": _seconds_to_us(row["duration"]),
            "bitrate": _positive_int(row["bitrate"]),
            "sample_rate": sample_rate,
            "file_format": (_text(row["filetype"]) or "").lower().strip("?") or None,
            "bpm": row["bpm"] if isinstance(row["bpm"], int | float) and row["bpm"] > 0 else None,
            "key": key_from_id(row["key_id"]),
            "key_original": _text(row["key"]),
            "rating": row["rating"] or None,
            "color": None if row["color"] is None else f"#{row['color'] & 0xFFFFFF:06X}",
            "play_count": row["timesplayed"] or None,
            "last_played": _datetime(row["last_played_at"]),
            "date_added": _date(row["datetime_added"]),
            "cues": self._cues(path, cue_rows, sample_rate, unmapped),
            "beatgrid": self._grid(path, row, sample_rate, unmapped),
        }
        try:
            location = self.path_mapping.to_library(path)
        except ValidationError as error:
            self.warnings.append(f"skipped Mixxx track {path!r}: {error.message}")
            return None
        return _build(
            lambda v: Track(path_origin=location, unmapped={NAME: unmapped}, **v),
            values,
            path,
            self.warnings,
        )

    def _cue_rows(self, db: sqlite3.Connection) -> dict[int, list[sqlite3.Row]]:
        rows: defaultdict[int, list[sqlite3.Row]] = defaultdict(list)
        for row in db.execute("SELECT * FROM cues ORDER BY track_id, hotcue, position, id"):
            rows[row["track_id"]].append(row)
        return rows

    def _cues(
        self,
        path: str,
        rows: list[sqlite3.Row],
        sample_rate: int | None,
        unmapped: dict[str, JSONValue],
    ) -> tuple[Cue, ...]:
        if not rows:
            return ()
        if sample_rate is None:
            self.warnings.append(f"{path}: cues skipped because the sample rate is unknown")
            return ()
        cues: list[Cue] = []
        slots: set[int] = set()
        for row in rows:
            kind, position, length, hotcue = (
                row["type"],
                row["position"],
                row["length"],
                row["hotcue"],
            )
            if kind in (_INTRO, _OUTRO):
                # Either end may be unset: the start as position -1, the end as length 0.
                marker: dict[str, JSONValue] = {}
                if position is not None and position >= 0:
                    marker["start_us"] = _samples_to_us(position, sample_rate)
                if position is not None and length:
                    marker["end_us"] = _samples_to_us(position + length, sample_rate)
                if marker:
                    unmapped["intro" if kind == _INTRO else "outro"] = marker
                continue
            if position is None or position < 0:
                self._skipped["cues without a position"] += 1
                continue
            start = _samples_to_us(position, sample_rate)
            end = _samples_to_us(position + (length or 0), sample_rate)
            slot = hotcue if hotcue is not None and hotcue >= 0 else None
            if slot is not None and slot in slots:
                self._skipped["cues on a pad already used"] += 1
                continue
            name = _text(row["label"])
            color = None if row["color"] is None else f"#{row['color'] & 0xFFFFFF:06X}"
            if kind == _HOT_CUE and slot is not None:
                cue = Cue(kind=CueKind.HOT, start_us=start, slot=slot, name=name, color=color)
            elif kind == _MAIN_CUE:
                cue = Cue(
                    kind=CueKind.MEMORY, start_us=start, name=name or MAIN_CUE_NAME, color=color
                )
            elif kind == _LOOP and end > start:
                cue = Cue(
                    kind=CueKind.LOOP, start_us=start, end_us=end, slot=slot, name=name, color=color
                )
            else:
                self._skipped["cues of kinds tunedex does not keep (beat, jump, silence)"] += 1
                continue
            if slot is not None:
                slots.add(slot)
            cues.append(cue)
        return tuple(cues)

    def _grid(
        self, path: str, row: sqlite3.Row, sample_rate: int | None, unmapped: dict[str, JSONValue]
    ) -> BeatGrid | None:
        blob, version = row["beats"], row["beats_version"]
        if not blob or not version:
            return None
        if sample_rate is None:
            self.warnings.append(f"{path}: beat grid skipped because the sample rate is unknown")
            return None
        try:
            return grid_from_mixxx(version, bytes(blob), sample_rate)
        except (KeyError, ProtobufError, ValidationError) as error:
            unmapped["beats"] = {
                "version": version,
                "sub_version": row["beats_sub_version"],
                "data": base64.b64encode(bytes(blob)).decode("ascii"),
            }
            reason = "unknown format" if isinstance(error, KeyError) else str(error)
            self.warnings.append(f"{path}: beat grid {version!r} not read ({reason})")
            return None

    # Playlists and crates

    def _playlists(self, db: sqlite3.Connection, tracks: dict[int, Track]) -> tuple[Node, ...]:
        dropped = 0

        def entries(track_ids: list[int]) -> tuple[TrackId, ...]:
            nonlocal dropped
            known = [tracks[t].id for t in track_ids if t in tracks]
            dropped += len(track_ids) - len(known)
            return tuple(known)

        members: defaultdict[int, list[int]] = defaultdict(list)
        for row in db.execute(
            "SELECT playlist_id, track_id FROM PlaylistTracks ORDER BY position, id"
        ):
            members[row["playlist_id"]].append(row["track_id"])
        playlists: list[Node] = []
        hidden = Counter[int]()
        for row in db.execute("SELECT * FROM Playlists ORDER BY position, id"):
            if row["hidden"] != 0:
                hidden[row["hidden"]] += 1
                continue
            playlists.append(
                Playlist(
                    name=row["name"] or f"Playlist {row['id']}",
                    entries=entries(members[row["id"]]),
                    unmapped={NAME: {"id": row["id"], "locked": bool(row["locked"])}},
                )
            )

        crate_members: defaultdict[int, list[int]] = defaultdict(list)
        for row in db.execute("SELECT crate_id, track_id FROM crate_tracks"):
            crate_members[row["crate_id"]].append(row["track_id"])
        crates: list[Node] = []
        for row in db.execute("SELECT * FROM crates ORDER BY name, id"):
            ordered = sorted(
                crate_members[row["id"]], key=lambda t: tracks[t].path if t in tracks else ""
            )
            crates.append(
                Playlist(
                    name=row["name"],
                    entries=entries(ordered),
                    unmapped={
                        NAME: {
                            "id": row["id"],
                            "locked": bool(row["locked"]),
                            "show": bool(row["show"]),
                        }
                    },
                )
            )

        left_out = [
            f"{hidden[_AUTO_DJ]} Auto DJ queue" if hidden[_AUTO_DJ] else "",
            f"{hidden[_HISTORY]} history playlists" if hidden[_HISTORY] else "",
        ]
        others = sum(n for kind, n in hidden.items() if kind not in (_AUTO_DJ, _HISTORY))
        if others:
            left_out.append(f"{others} other hidden playlists")
        if any(left_out):
            self.warnings.append(f"not imported: {', '.join(p for p in left_out if p)}")
        if dropped:
            self.warnings.append(f"{dropped} playlist entries point at tracks that were not read")
        return (
            Folder(name="Playlists", children=tuple(playlists)),
            Folder(name="Crates", children=tuple(crates)),
        )

    def _report_skipped(self) -> None:
        for reason, count in self._skipped.items():
            self.warnings.append(f"{count} {reason} were skipped")


def _build(
    make: Callable[[dict[str, Any]], Track], values: dict[str, Any], path: str, warnings: list[str]
) -> Track:
    """Build a track, dropping (with a warning) any value the model rejects."""
    values = dict(values)
    while True:
        try:
            return make(values)
        except ValidationError as error:
            if error.field not in values:
                raise
            warnings.append(f"{path}: ignored invalid {error.field} ({error.message})")
            del values[error.field]


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _match_int(pattern: re.Pattern[str], value: object) -> int | None:
    match = pattern.match(value) if isinstance(value, str) else None
    return int(match.group(1)) if match else None


def _positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _seconds_to_us(value: object) -> int | None:
    if not isinstance(value, int | float) or value <= 0:
        return None
    return round(value * 1_000_000)


def _samples_to_us(samples: float, sample_rate: int) -> int:
    """Mixxx positions count both stereo channels: two samples per frame."""
    return round(samples / 2 / sample_rate * 1_000_000)


def _datetime(value: object) -> datetime.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.UTC)


def _date(value: object) -> datetime.date | None:
    parsed = _datetime(value)
    return None if parsed is None else parsed.date()
