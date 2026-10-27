"""Building Mixxx library databases for tests, from the real schema 39.

Beat grids are encoded here with a protobuf writer of our own, independent of the
adapter's decoder.
"""

import sqlite3
import struct
from collections.abc import Sequence
from pathlib import Path

SCHEMA = Path(__file__).parents[1] / "fixtures" / "mixxx" / "schema-39.sql"

# Mixxx cue types.
HOT_CUE, MAIN_CUE, BEAT, LOOP, JUMP, INTRO, OUTRO, N60DB = 1, 2, 3, 4, 5, 6, 7, 8


def _varint(value: int) -> bytes:
    out = bytearray()
    value &= (1 << 64) - 1
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _field(number: int, wire: int, payload: bytes) -> bytes:
    if wire == 2:
        payload = _varint(len(payload)) + payload
    return _varint(number << 3 | wire) + payload


def beat_grid(bpm: float, first_beat_frame: int) -> bytes:
    """``BeatGrid { Bpm bpm = 1 { double bpm }; Beat first_beat = 2 { int32 frame_position } }``"""
    bpm_message = _field(1, 1, struct.pack("<d", bpm))
    beat_message = _field(1, 0, _varint(first_beat_frame))
    return _field(1, 2, bpm_message) + _field(2, 2, beat_message)


def beat_map(frames: Sequence[int], disabled: Sequence[int] = ()) -> bytes:
    """``BeatMap { repeated Beat beat = 1 { int32 frame_position = 1; bool enabled = 2 } }``"""
    out = b""
    for frame in frames:
        beat = _field(1, 0, _varint(frame))
        if frame in disabled:
            beat += _field(2, 0, _varint(0))
        out += _field(1, 2, beat)
    return out


class MixxxDatabase:
    """A Mixxx database under construction. Rows are written immediately."""

    def __init__(self, path: Path, *, schema_version: int = 39) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.db.execute(
            "UPDATE settings SET value = ? WHERE name = 'mixxx.schema.version'",
            (str(schema_version),),
        )
        # Mixxx creates the Auto DJ queue on first start.
        self.db.execute(
            "INSERT INTO Playlists (id, name, position, hidden) VALUES (1, 'Auto DJ', 1, 1)"
        )
        self.db.commit()

    def add_track(
        self,
        location: str,
        *,
        removed: bool = False,
        missing: bool = False,
        samplerate: int | None = 44100,
        **columns: object,
    ) -> int:
        cursor = self.db.execute(
            "INSERT INTO track_locations (location, filename, directory, filesize, fs_deleted,"
            " needs_verification) VALUES (?, ?, ?, 1000, ?, 0)",
            (location, location.rsplit("/", 1)[-1], location.rsplit("/", 1)[0], int(missing)),
        )
        values: dict[str, object] = {
            "location": cursor.lastrowid,
            "samplerate": samplerate,
            "mixxx_deleted": int(removed),
            "filetype": "mp3",
            **columns,
        }
        names = ", ".join(values)
        marks = ", ".join("?" * len(values))
        cursor = self.db.execute(
            f"INSERT INTO library ({names}) VALUES ({marks})", tuple(values.values())
        )
        self.db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def add_cue(
        self,
        track_id: int,
        kind: int,
        position: int,
        *,
        length: int = 0,
        hotcue: int = -1,
        label: str = "",
        color: int = 0xFF0000,
    ) -> None:
        self.db.execute(
            "INSERT INTO cues (track_id, type, position, length, hotcue, label, color)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (track_id, kind, position, length, hotcue, label, color),
        )
        self.db.commit()

    def set_beats(self, track_id: int, blob: bytes, version: str = "BeatGrid-2.0") -> None:
        self.db.execute(
            "UPDATE library SET beats = ?, beats_version = ? WHERE id = ?",
            (blob, version, track_id),
        )
        self.db.commit()

    def add_playlist(self, name: str, track_ids: Sequence[int], *, hidden: int = 0) -> int:
        (position,) = self.db.execute(
            "SELECT coalesce(max(position), 0) + 1 FROM Playlists"
        ).fetchone()
        cursor = self.db.execute(
            "INSERT INTO Playlists (name, position, hidden, date_created, date_modified, locked)"
            " VALUES (?, ?, ?, '2026-10-27 12:00:00', '2026-10-27 12:00:00', 0)",
            (name, position, hidden),
        )
        playlist_id = cursor.lastrowid
        self.db.executemany(
            "INSERT INTO PlaylistTracks (playlist_id, track_id, position, pl_datetime_added)"
            " VALUES (?, ?, ?, '2026-10-27 12:00:00')",
            ((playlist_id, t, i + 1) for i, t in enumerate(track_ids)),
        )
        self.db.commit()
        assert playlist_id is not None
        return playlist_id

    def add_crate(self, name: str, track_ids: Sequence[int]) -> int:
        cursor = self.db.execute(
            "INSERT INTO crates (name, count) VALUES (?, ?)", (name, len(track_ids))
        )
        crate_id = cursor.lastrowid
        self.db.executemany(
            "INSERT INTO crate_tracks (crate_id, track_id) VALUES (?, ?)",
            ((crate_id, t) for t in track_ids),
        )
        self.db.commit()
        assert crate_id is not None
        return crate_id

    def close(self) -> None:
        self.db.close()
