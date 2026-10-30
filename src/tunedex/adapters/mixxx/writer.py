"""Planning writes to a Mixxx library database (schema 39, Mixxx 2.5).

The current file is read once, hashed and loaded into memory; the edits are made to
that copy, and the plan carries the whole new file. Only rows and columns tunedex owns
are touched, so everything else Mixxx keeps stays exactly as it was. The edited copy is
read back to give the plan's view: what Mixxx will hold of the written data.
"""

import datetime
import hashlib
import posixpath
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from tunedex.adapters.contract import Capabilities, FileChange, WriteOptions, WritePlan
from tunedex.adapters.errors import AdapterError
from tunedex.adapters.losses import LossCollector, compute_losses, display_name
from tunedex.adapters.mixxx import reader
from tunedex.adapters.mixxx.beats import grid_from_mixxx, grid_to_mixxx
from tunedex.adapters.mixxx.keys import KEY_MAP, encode_key_map, key_to_id
from tunedex.adapters.pathmap import PathMapping
from tunedex.model.beatgrid import BeatGrid
from tunedex.model.cue import Cue, CueKind
from tunedex.model.ids import NodeId, TrackId, new_node_id
from tunedex.model.key import Key
from tunedex.model.library import Library
from tunedex.model.playlist import Folder, Node, Playlist
from tunedex.model.track import Track

HOT_CUES = 36
# cues.type values tunedex writes; the other kinds are left alone.
_HOT_CUE, _MAIN_CUE, _LOOP = 1, 2, 4
_OWN_CUE_TYPES = (_HOT_CUE, _MAIN_CUE, _LOOP)
_DEFAULT_CUE_COLOR = 0xFFFF0000  # the cues.color column default
_SAMPLE_TOLERANCE = 1.0  # positions closer than this are the same cue

_TEXT_COLUMNS = {
    "artist": "artist",
    "title": "title",
    "album": "album",
    "album_artist": "album_artist",
    "genre": "genre",
    "composer": "composer",
    "grouping": "grouping",
    "comment": "comment",
}
UPDATED_FIELDS = frozenset(
    {*_TEXT_COLUMNS, "year", "track_number", "rating", "color", "bpm", "key"}
)

Probe = Callable[[], bool]
# A cues row: type, position, length, hotcue, label, color.
_CueRow = tuple[int, float, float, int, str, int]


def journal_path(path: Path) -> Path:
    return path.with_name(f"{path.name}-journal")


def ensure_closed(path: Path, running: Probe) -> None:
    """Raise when Mixxx runs or the database has a rollback journal next to it."""
    if running():
        raise AdapterError("Mixxx is running; quit Mixxx and try again")
    if journal_path(path).exists():
        raise AdapterError(
            f"{journal_path(path)} exists, so Mixxx is running or did not close properly;"
            " start and quit Mixxx once, then try again"
        )


@dataclass(frozen=True, slots=True)
class _List:
    """A Mixxx playlist or crate that a library node is written to."""

    kind: str  # "playlist" or "crate"
    name: str
    hint: int | None  # the Mixxx id the node was imported from


@dataclass
class _Existing:
    mixxx_id: int
    location: str
    deleted: bool
    sample_rate: int | None
    duration: float | None


@dataclass
class MixxxWriter:
    capabilities: Capabilities
    running: Probe
    path_mapping: PathMapping = field(default_factory=PathMapping)
    now: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(datetime.UTC))
    warnings: list[str] = field(default_factory=list[str])
    losses: LossCollector = field(default_factory=LossCollector)

    def plan(self, library: Library, location: Path, options: WriteOptions) -> WritePlan:
        self.path_mapping = options.path_mapping
        path = reader.database_path(location)
        if not path.is_file():
            raise AdapterError(f"no Mixxx library at {path}; start Mixxx once to create it")
        ensure_closed(path, self.running)
        content = path.read_bytes()
        base = hashlib.sha256(content).hexdigest()
        db = sqlite3.connect(":memory:")
        try:
            db.deserialize(content)
            self._check_version(db, path)
            before = db.total_changes
            with db:
                current = reader.MixxxReader(self.path_mapping).read_rows(db)
                tracks, nodes = self._selection(library, options.selection)
                ids = self._write_tracks(db, library, tracks, current[0])
                written = self._write_lists(db, library, nodes, ids, options.source_root)
            changed = db.total_changes != before
            # Unchanged, the database reads back as it read before the edits.
            after = reader.MixxxReader(self.path_mapping).read_rows(db) if changed else current
            view = _view(after, set(ids.values()), written)
            if changed:
                (check,) = db.execute("PRAGMA integrity_check").fetchone()
                if check != "ok":
                    raise AdapterError(f"the edited Mixxx database is damaged: {check}")
                new_content = db.serialize()
        finally:
            db.close()

        compute_losses(
            library,
            list(tracks),
            [n for n in nodes if not isinstance(n, Folder)],
            self.capabilities,
            reader.NAME,
            self.losses,
        )
        changes: tuple[FileChange, ...] = ()
        if changed:
            description = "update the Mixxx library"
            changes = (FileChange(path=path, content=new_content, base_sha256=base,  # pyright: ignore[reportPossiblyUnboundVariable]
                                  description=description),)  # fmt: skip
        return WritePlan(
            adapter=reader.NAME,
            location=location,
            changes=changes,
            losses=self.losses.losses(),
            warnings=tuple(self.warnings),
            view=view,
            check=lambda: ensure_closed(path, self.running),
        )

    def _check_version(self, db: sqlite3.Connection, path: Path) -> None:
        try:
            row = db.execute(
                "SELECT value FROM settings WHERE name = 'mixxx.schema.version'"
            ).fetchone()
        except sqlite3.Error:
            row = None
        version = None if row is None else str(row[0])
        if version != str(reader.SUPPORTED_SCHEMA):
            raise AdapterError(
                f"{path}: writing needs Mixxx schema version {reader.SUPPORTED_SCHEMA}"
                f" (Mixxx 2.5), found {version or 'none'}"
            )

    # What to write

    def _selection(
        self, library: Library, selection: frozenset[NodeId] | None
    ) -> tuple[dict[TrackId, Track], list[Node]]:
        """The tracks and nodes to write: everything, or the selected nodes and their tracks."""
        parents = {node.id: parent for parent, _index, node in library.walk()}

        def selected(node_id: NodeId) -> bool:
            current: NodeId | None = node_id
            while current is not None:
                if selection is not None and current in selection:
                    return True
                current = parents.get(current)
            return selection is None

        nodes = [node for _parent, _index, node in library.walk() if selected(node.id)]
        if selection is None:
            tracks = dict(library.tracks)
        else:
            entries = [e for n in nodes if isinstance(n, Playlist) for e in n.entries]
            tracks = {e: library.tracks[e] for e in dict.fromkeys(entries)}
        return tracks, nodes

    # Tracks

    def _write_tracks(
        self,
        db: sqlite3.Connection,
        library: Library,
        tracks: Mapping[TrackId, Track],
        current: Mapping[int, Track],
    ) -> dict[TrackId, int]:
        """Write ``tracks``; returns the Mixxx id of each one written."""
        existing = {
            row[1]: _Existing(row[0], row[1], bool(row[2]), row[3], row[4])
            for row in db.execute(
                "SELECT library.id, track_locations.location, coalesce(library.mixxx_deleted, 0),"
                " library.samplerate, library.duration FROM library"
                " JOIN track_locations ON library.location = track_locations.id"
            )
        }
        placeholders = ", ".join("?" * len(_OWN_CUE_TYPES))
        cues: dict[int, list[_CueRow]] = {}
        for row in db.execute(
            "SELECT track_id, type, position, length, hotcue, label, color FROM cues"
            f" WHERE type IN ({placeholders}) ORDER BY id",
            _OWN_CUE_TYPES,
        ):
            cues.setdefault(row[0], []).append(tuple(row[1:]))
        ids: dict[TrackId, int] = {}
        for track in sorted(tracks.values(), key=lambda t: t.path):
            location = self.path_mapping.to_target(track.path)
            row = existing.get(location)
            if row is not None and row.deleted:
                self.losses.add(
                    "removed-in-mixxx",
                    "tracks removed from the Mixxx library are not brought back",
                    display_name(track),
                )
                continue
            if row is None:
                mixxx_id = self._insert_track(db, track, location)
                old = None
                sample_rate, duration = track.sample_rate, _seconds(track.duration_us)
            else:
                mixxx_id = row.mixxx_id
                old = current.get(mixxx_id)
                sample_rate = row.sample_rate if row.sample_rate else track.sample_rate
                duration = row.duration if row.duration else _seconds(track.duration_us)
                self._update_track(db, mixxx_id, track, old)
            self._write_cues(db, mixxx_id, track, sample_rate, cues.get(mixxx_id, []))
            self._write_grid(db, mixxx_id, track, old, sample_rate, duration)
            ids[track.id] = mixxx_id
        return ids

    def _update_track(
        self, db: sqlite3.Connection, mixxx_id: int, track: Track, old: Track | None
    ) -> None:
        columns: dict[str, object] = {}
        for name in sorted(UPDATED_FIELDS):
            value = getattr(track, name)
            if old is not None and getattr(old, name) == value:
                continue
            columns.update(_columns(name, value))
        if columns:
            assignments = ", ".join(f"{column} = ?" for column in columns)
            db.execute(
                f"UPDATE library SET {assignments} WHERE id = ?", (*columns.values(), mixxx_id)
            )

    def _insert_track(self, db: sqlite3.Connection, track: Track, location: str) -> int:
        file = Path(location)
        try:
            stat = file.stat()
            size, synchronized = stat.st_size, int(stat.st_mtime * 1000)
        except OSError:
            size, synchronized = 0, None
        cursor = db.execute(
            "INSERT INTO track_locations (location, filename, directory, filesize, fs_deleted,"
            " needs_verification) VALUES (?, ?, ?, ?, 0, 0)",
            (location, posixpath.basename(location), posixpath.dirname(location), size),
        )
        columns: dict[str, object] = {
            "location": cursor.lastrowid,
            "mixxx_deleted": 0,
            "header_parsed": 1,
            "source_synchronized_ms": synchronized,
            "datetime_added": _added(
                datetime.datetime.combine(track.date_added, datetime.time(), datetime.UTC)
                if track.date_added
                else self.now
            ),
            "channels": 2,
            "duration": _seconds(track.duration_us) or 0,
            "bitrate": track.bitrate or 0,
            "samplerate": track.sample_rate or 0,
            "filetype": track.file_format or "?",
            "timesplayed": track.play_count or 0,
            "played": 0,
            "last_played_at": _timestamp(track.last_played) if track.last_played else None,
        }
        for name in sorted(UPDATED_FIELDS):
            columns.update(_columns(name, getattr(track, name)))
        names = ", ".join(columns)
        marks = ", ".join("?" * len(columns))
        cursor = db.execute(f"INSERT INTO library ({names}) VALUES ({marks})", (*columns.values(),))
        return _row_id(cursor)

    def _write_cues(
        self,
        db: sqlite3.Connection,
        mixxx_id: int,
        track: Track,
        sample_rate: int | None,
        current: list[_CueRow],
    ) -> None:
        if not sample_rate:
            if track.cues:
                self.warnings.append(
                    f"{track.path}: cues not written because the sample rate is unknown"
                )
            return
        wanted = self._cue_rows(track, sample_rate)
        if _same_cues(current, wanted):
            return
        placeholders = ", ".join("?" * len(_OWN_CUE_TYPES))
        db.execute(
            f"DELETE FROM cues WHERE track_id = ? AND type IN ({placeholders})",
            (mixxx_id, *_OWN_CUE_TYPES),
        )
        db.executemany(
            "INSERT INTO cues (track_id, type, position, length, hotcue, label, color)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            ((mixxx_id, *row) for row in wanted),
        )
        main = [row for row in wanted if row[0] == _MAIN_CUE]
        db.execute(
            "UPDATE library SET cuepoint = ? WHERE id = ?",
            (round(main[0][1]) if main else 0, mixxx_id),
        )

    def _cue_rows(self, track: Track, sample_rate: int) -> list[_CueRow]:
        rows: list[_CueRow] = []
        memory = 0
        for cue in track.cues:
            position = _samples(cue.start_us, sample_rate)
            if cue.slot is not None and cue.slot >= HOT_CUES:
                self.losses.add(
                    "pads-beyond-36", f"Mixxx has {HOT_CUES} hot cue pads", display_name(track)
                )
                continue
            if cue.kind is CueKind.HOT:
                rows.append(_cue_row(_HOT_CUE, position, 0, cue))
            elif cue.kind is CueKind.MEMORY:
                memory += 1
                if memory > 1:
                    self.losses.add(
                        "memory-cues",
                        "Mixxx keeps one memory cue (the main cue); the others",
                        display_name(track),
                    )
                    continue
                label = "" if cue.name in (None, reader.MAIN_CUE_NAME) else cue.name
                rows.append((_MAIN_CUE, position, 0, -1, label or "", _color(cue)))
            elif cue.kind is CueKind.LOOP and cue.end_us is not None:
                length = _samples(cue.end_us, sample_rate) - position
                rows.append(_cue_row(_LOOP, position, length, cue))
        return rows

    def _write_grid(
        self,
        db: sqlite3.Connection,
        mixxx_id: int,
        track: Track,
        old: Track | None,
        sample_rate: int | None,
        duration: float | None,
    ) -> None:
        grid = track.beatgrid
        if grid is None or (old is not None and old.beatgrid == grid):
            return
        if not sample_rate:
            self.warnings.append(
                f"{track.path}: beat grid not written because the sample rate is unknown"
            )
            return
        if any(marker.beat != 1 for marker in grid.markers[:1]):
            self.losses.add(
                "grid-bar-position",
                "Mixxx grids do not keep the bar position of the first beat",
                display_name(track),
            )
        frames = None if not duration else round(duration * sample_rate)
        encoded = grid_to_mixxx(grid, sample_rate, frames)
        if encoded is None:
            self.warnings.append(
                f"{track.path}: beat grid with tempo changes not written because"
                " the duration is unknown"
            )
            return
        version, blob = encoded
        if old is not None and old.beatgrid == _decoded(version, blob, sample_rate):
            return
        db.execute(
            "UPDATE library SET beats = ?, beats_version = ?,"
            " beats_sub_version = coalesce(beats_sub_version, '') WHERE id = ?",
            (blob, version, mixxx_id),
        )

    # Playlists and crates

    def _write_lists(
        self,
        db: sqlite3.Connection,
        library: Library,
        nodes: Iterable[Node],
        ids: Mapping[TrackId, int],
        source_root: NodeId | None,
    ) -> dict[tuple[str, int], NodeId]:
        """Write the playlists; returns the tunedex node of each written Mixxx list."""
        paths = _paths(library)
        root = paths.get(source_root) if source_root is not None else None
        playlists = _lists(db, "SELECT id, name, locked FROM Playlists WHERE hidden = 0"
                           " ORDER BY position, id")  # fmt: skip
        crates = _lists(db, "SELECT id, name, locked FROM crates ORDER BY name, id")
        written: dict[tuple[str, int], NodeId] = {}
        for node in nodes:
            if not isinstance(node, Playlist):
                continue
            target = _target(node, paths[node.id], root)
            known = playlists if target.kind == "playlist" else crates
            mixxx_id = self._find(known, target)
            if mixxx_id is not None and (target.kind, mixxx_id) in written:
                self.warnings.append(
                    f"{'/'.join(paths[node.id])} not written: another playlist already"
                    f" writes the Mixxx {target.kind} {target.name!r}"
                )
                continue
            if mixxx_id is not None and known[mixxx_id][1]:
                self.warnings.append(
                    f"the Mixxx {target.kind} {known[mixxx_id][0]!r} is locked and was not changed"
                )
                continue
            entries = [ids[e] for e in node.entries if e in ids]
            if target.kind == "playlist":
                mixxx_id = self._write_playlist(db, mixxx_id, target.name, entries)
            else:
                mixxx_id = self._write_crate(db, mixxx_id, target.name, entries)
            known[mixxx_id] = (target.name, False)
            written[(target.kind, mixxx_id)] = node.id
        return written

    @staticmethod
    def _find(known: Mapping[int, tuple[str, bool]], target: _List) -> int | None:
        if target.hint is not None and target.hint in known:
            return target.hint
        for mixxx_id, (name, _locked) in known.items():
            if name == target.name:
                return mixxx_id
        return None

    def _write_playlist(
        self, db: sqlite3.Connection, mixxx_id: int | None, name: str, entries: list[int]
    ) -> int:
        now = _timestamp(self.now)
        if mixxx_id is None:
            (position,) = db.execute(
                "SELECT coalesce(max(position), 0) + 1 FROM Playlists"
            ).fetchone()
            cursor = db.execute(
                "INSERT INTO Playlists (name, position, hidden, date_created, date_modified,"
                " locked) VALUES (?, ?, 0, ?, ?, 0)",
                (name, position, now, now),
            )
            mixxx_id = _row_id(cursor)
        else:
            db.execute(
                "UPDATE Playlists SET name = ? WHERE id = ? AND name IS NOT ?",
                (name, mixxx_id, name),
            )
        current = [
            row[0]
            for row in db.execute(
                "SELECT track_id FROM PlaylistTracks WHERE playlist_id = ? ORDER BY position, id",
                (mixxx_id,),
            )
        ]
        if current != entries:
            db.execute("DELETE FROM PlaylistTracks WHERE playlist_id = ?", (mixxx_id,))
            db.executemany(
                "INSERT INTO PlaylistTracks (playlist_id, track_id, position, pl_datetime_added)"
                " VALUES (?, ?, ?, ?)",
                ((mixxx_id, track, index + 1, now) for index, track in enumerate(entries)),
            )
            db.execute("UPDATE Playlists SET date_modified = ? WHERE id = ?", (now, mixxx_id))
        return mixxx_id

    def _write_crate(
        self, db: sqlite3.Connection, mixxx_id: int | None, name: str, entries: list[int]
    ) -> int:
        if mixxx_id is None:
            cursor = db.execute(
                "INSERT INTO crates (name, count, show, locked) VALUES (?, 0, 1, 0)", (name,)
            )
            mixxx_id = _row_id(cursor)
        else:
            db.execute(
                "UPDATE crates SET name = ? WHERE id = ? AND name IS NOT ?", (name, mixxx_id, name)
            )
        wanted = set(entries)
        current = {
            row[0]
            for row in db.execute(
                "SELECT track_id FROM crate_tracks WHERE crate_id = ?", (mixxx_id,)
            )
        }
        if current != wanted:
            db.executemany(
                "DELETE FROM crate_tracks WHERE crate_id = ? AND track_id = ?",
                ((mixxx_id, t) for t in sorted(current - wanted)),
            )
            db.executemany(
                "INSERT INTO crate_tracks (crate_id, track_id) VALUES (?, ?)",
                ((mixxx_id, t) for t in sorted(wanted - current)),
            )
            db.execute(
                "UPDATE crates SET count = ? WHERE id = ? AND count IS NOT ?",
                (len(wanted), mixxx_id, len(wanted)),
            )
        return mixxx_id


def _view(
    read: tuple[dict[int, Track], tuple[Node, ...]],
    track_ids: set[int],
    written: Mapping[tuple[str, int], NodeId],
) -> Library:
    """The written tracks and lists as Mixxx holds them, in the reader's shape."""
    tracks, folders = read
    kept = {mixxx_id: t for mixxx_id, t in tracks.items() if mixxx_id in track_ids}
    kept_ids = {t.id for t in kept.values()}
    kinds = {"Playlists": "playlist", "Crates": "crate"}
    view_folders: list[Node] = []
    for folder in folders:
        if not isinstance(folder, Folder):
            continue
        kind = kinds[folder.name]
        children: list[Node] = []
        for child in folder.children:
            data = child.unmapped.get(reader.NAME)
            mixxx_id = data.get("id") if isinstance(data, dict) else None
            node_id = written.get((kind, mixxx_id)) if isinstance(mixxx_id, int) else None
            if node_id is not None and isinstance(child, Playlist):
                entries = tuple(e for e in child.entries if e in kept_ids)
                children.append(
                    Playlist(id=node_id, name=child.name, entries=entries, unmapped=child.unmapped)
                )
        view_folders.append(Folder(id=new_node_id(), name=folder.name, children=tuple(children)))
    return Library.build(kept.values(), view_folders)


def _row_id(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise AdapterError("SQLite gave no id for an inserted row")
    return cursor.lastrowid


def _lists(db: sqlite3.Connection, query: str) -> dict[int, tuple[str, bool]]:
    return {row[0]: (row[1] or "", bool(row[2])) for row in db.execute(query)}


def _paths(library: Library) -> dict[NodeId, tuple[str, ...]]:
    paths: dict[NodeId, tuple[str, ...]] = {}
    for parent, _index, node in library.walk():
        paths[node.id] = (*(paths[parent] if parent is not None else ()), node.name)
    return paths


def _target(node: Playlist, path: tuple[str, ...], root: tuple[str, ...] | None) -> _List:
    """Where a playlist goes in Mixxx: back where it came from, or a playlist named by path."""
    if root is not None and path[: len(root)] == root and len(path) > len(root):
        inner = path[len(root) :]
        data = node.unmapped.get(reader.NAME)
        hint = data.get("id") if isinstance(data, dict) else None
        hint = hint if isinstance(hint, int) else None
        if inner[0] in ("Playlists", "Crates") and len(inner) > 1:
            kind = "playlist" if inner[0] == "Playlists" else "crate"
            return _List(kind, " / ".join(inner[1:]), hint)
        return _List("playlist", " / ".join(inner), None)
    return _List("playlist", " / ".join(path), None)


def _columns(name: str, value: object) -> dict[str, object]:
    """The library columns holding the field ``name``."""
    if name in _TEXT_COLUMNS:
        return {_TEXT_COLUMNS[name]: value or ""}
    if name == "year":
        return {"year": "" if value is None else str(value)}
    if name == "track_number":
        return {"tracknumber": "" if value is None else str(value)}
    if name == "rating":
        return {"rating": value or 0}
    if name == "color":
        return {"color": None if not isinstance(value, str) else int(value[1:], 16)}
    if name == "bpm":
        return {"bpm": value or 0}
    if name == "key":
        if value is None:
            return {"key": "", "key_id": 0, "keys": None, "keys_version": None,
                    "keys_sub_version": None}  # fmt: skip
        if not isinstance(value, Key):
            raise TypeError(f"not a key: {value!r}")
        key_id, text = key_to_id(value), value.open_key()
        return {"key": text, "key_id": key_id, "keys": encode_key_map(key_id, text),
                "keys_version": KEY_MAP, "keys_sub_version": ""}  # fmt: skip
    raise KeyError(name)


def _cue_row(kind: int, position: float, length: float, cue: Cue) -> _CueRow:
    return (kind, position, length, -1 if cue.slot is None else cue.slot, cue.name or "",
            _color(cue))  # fmt: skip


def _color(cue: Cue) -> int:
    return _DEFAULT_CUE_COLOR if cue.color is None else int(cue.color[1:], 16)


def _same_cues(current: list[_CueRow], wanted: list[_CueRow]) -> bool:
    if len(current) != len(wanted):
        return False
    remaining = list(current)
    for row in wanted:
        match = next((c for c in remaining if _same_cue(c, row)), None)
        if match is None:
            return False
        remaining.remove(match)
    return True


def _same_cue(a: _CueRow, b: _CueRow) -> bool:
    close = abs(a[1] - b[1]) < _SAMPLE_TOLERANCE and abs(a[2] - b[2]) < _SAMPLE_TOLERANCE
    # Mixxx may keep an alpha channel in colours; tunedex reads and writes RGB.
    same_color = a[5] & 0xFFFFFF == b[5] & 0xFFFFFF
    return close and same_color and (a[0], a[3], a[4]) == (b[0], b[3], b[4])


def _decoded(version: str, blob: bytes, sample_rate: int) -> BeatGrid | None:
    return grid_from_mixxx(version, blob, sample_rate)


def _samples(position_us: int, sample_rate: int) -> float:
    """Mixxx positions count both stereo channels: two samples per frame."""
    return position_us * sample_rate * 2 / 1_000_000


def _seconds(duration_us: int | None) -> float | None:
    return None if duration_us is None else duration_us / 1_000_000


def _added(moment: datetime.datetime) -> str:
    """``datetime_added`` as Mixxx writes it: ISO 8601 in UTC with milliseconds."""
    utc = moment.astimezone(datetime.UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def _timestamp(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")
