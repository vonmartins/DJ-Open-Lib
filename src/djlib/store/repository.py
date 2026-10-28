"""Reading and writing the canonical library in a djlib database."""

import contextlib
import datetime
import json
import sqlite3
import uuid
from collections import defaultdict
from collections.abc import Generator, Iterable, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from djlib.model.beatgrid import BeatGrid, BeatMarker
from djlib.model.cue import Cue, CueKind
from djlib.model.errors import ValidationError
from djlib.model.ids import NodeId, TrackId
from djlib.model.key import Key
from djlib.model.library import Library
from djlib.model.paths import normalize_path
from djlib.model.playlist import Folder, MatchMode, Node, Playlist, Rule, Smartlist
from djlib.model.track import DATE_FIELDS, INT_FIELDS, TEXT_FIELDS, Track
from djlib.model.unmapped import JSONValue
from djlib.store.database import open_database, transaction
from djlib.store.errors import ConflictError, NotFoundError
from djlib.store.file_state import FileState
from djlib.store.migrations import Migration
from djlib.store.operations import (
    AddImportedTrack,
    AddTrack,
    LibraryOperation,
    MarkMissing,
    MarkPresent,
    MoveTrack,
    RecordSourceValues,
    RefreshState,
    RegisterSource,
    ReplaceSourceFolder,
    UpdateImportedTrack,
    UpdateTrack,
)
from djlib.store.source_state import SourceInfo

Row = tuple[Any, ...]

# Track fields stored as-is, in column order after id, path and path_origin.
_PLAIN_FIELDS = (*TEXT_FIELDS, *INT_FIELDS, "bpm", "color")
_TRACK_COLUMNS = (
    "id",
    "path",
    "path_origin",
    *_PLAIN_FIELDS,
    "key_code",
    *DATE_FIELDS,
    "last_played",
    "unmapped",
)
_TRACK_SELECT = f"SELECT {', '.join(_TRACK_COLUMNS)} FROM tracks"
_TRACK_INSERT = (
    f"INSERT INTO tracks ({', '.join(_TRACK_COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(_TRACK_COLUMNS))})"
)
_TRACK_UPDATE = (
    f"UPDATE tracks SET {', '.join(f'{c} = ?' for c in _TRACK_COLUMNS[1:])} WHERE id = ?"
)
_NODE_COLUMNS = "id, parent_id, position, kind, name, match_mode, unmapped"
_FILE_STATE_COLUMNS = "track_id, size, mtime_ns, quick_hash, missing, scanned_at, scanned_values"
_SUBTREE = """
    WITH RECURSIVE subtree(id) AS (
        SELECT id FROM playlist_nodes WHERE id = ?
        UNION ALL
        SELECT n.id FROM playlist_nodes n JOIN subtree s ON n.parent_id = s.id
    )
"""


class Store:
    """A djlib database holding one canonical library.

    Every method that writes runs in a single transaction: it either completes or
    leaves the database unchanged.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection

    @classmethod
    def open(cls, path: str | Path, migrations: Sequence[Migration] | None = None) -> Self:
        """Open or create the database at ``path`` (see ``open_database``)."""
        return cls(open_database(Path(path), migrations))

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def path(self) -> Path | None:
        """The database file, or ``None`` for an in-memory store."""
        rows = self._db.execute("PRAGMA database_list").fetchall()
        file = next((row[2] for row in rows if row[1] == "main"), "")
        return Path(file) if file else None

    def revision(self) -> int:
        """A number that increases with every committed write to library content."""
        (revision,) = self._db.execute("SELECT revision FROM store_meta").fetchone()
        return revision

    @contextlib.contextmanager
    def _write(self) -> Generator[None]:
        """A write transaction to library content, which increments the revision."""
        with transaction(self._db):
            yield
            self._db.execute("UPDATE store_meta SET revision = revision + 1")

    # Tracks

    def add_track(self, track: Track) -> None:
        with self._write():
            self._check_path_free(track)
            try:
                self._insert_tracks([track])
            except sqlite3.IntegrityError as error:
                raise ConflictError(f"track {track.id} already exists") from error

    def get_track(self, track_id: TrackId) -> Track:
        tracks = self._load_tracks("WHERE id = ?", (str(track_id),))
        if not tracks:
            raise NotFoundError(f"track {track_id} does not exist")
        return tracks[0]

    def find_track_by_path(self, path: str) -> Track | None:
        """Return the track whose normalized path equals the normalized form of ``path``."""
        tracks = self._load_tracks("WHERE path = ?", (normalize_path(path),))
        return tracks[0] if tracks else None

    def list_tracks(self) -> list[Track]:
        return self._load_tracks()

    def list_tracks_under(self, root: str) -> list[Track]:
        """Tracks whose normalized path lies below the directory ``root``."""
        prefix = normalize_path(root).rstrip("/") + "/"
        return self._load_tracks("WHERE substr(path, 1, ?) = ?", (len(prefix), prefix))

    def update_track(self, track: Track) -> None:
        """Replace the stored track, including its cues, beatgrid and tags."""
        with self._write():
            self._replace_track(track)

    def _replace_track(self, track: Track) -> None:
        self._check_path_free(track)
        cursor = self._db.execute(_TRACK_UPDATE, (*_track_row(track)[1:], str(track.id)))
        if cursor.rowcount == 0:
            raise NotFoundError(f"track {track.id} does not exist")
        for table in ("cues", "beat_markers", "track_tags"):
            self._db.execute(f"DELETE FROM {table} WHERE track_id = ?", (str(track.id),))
        self._insert_track_children([track])
        self._delete_orphan_tags()

    # File state and scans

    def file_state(self, track_id: TrackId) -> FileState | None:
        rows = self._db.execute(
            f"SELECT {_FILE_STATE_COLUMNS} FROM file_state WHERE track_id = ?", (str(track_id),)
        ).fetchall()
        return _file_state_from_row(rows[0]) if rows else None

    def file_states(self, root: str) -> dict[TrackId, FileState]:
        """File states of the tracks below the directory ``root``."""
        prefix = normalize_path(root).rstrip("/") + "/"
        rows = self._db.execute(
            f"SELECT {_FILE_STATE_COLUMNS} FROM file_state"
            " WHERE track_id IN (SELECT id FROM tracks WHERE substr(path, 1, ?) = ?)",
            (len(prefix), prefix),
        ).fetchall()
        states = [_file_state_from_row(row) for row in rows]
        return {state.track_id: state for state in states}

    def apply_operations(
        self, operations: Sequence[LibraryOperation], *, expected_revision: int | None = None
    ) -> None:
        """Apply every operation in one transaction, or none if any of them fails.

        With ``expected_revision``, applying fails unless the store is at that revision.
        Sources are registered before the other operations run.
        """
        with self._write():
            if expected_revision is not None and self.revision() != expected_revision:
                raise ConflictError(
                    f"the library changed since the plan was made (revision"
                    f" {self.revision()}, expected {expected_revision})"
                )
            ordered = sorted(operations, key=lambda op: not isinstance(op, RegisterSource))
            for operation in ordered:
                self._apply_operation(operation)

    apply_scan = apply_operations

    def _apply_operation(self, operation: LibraryOperation) -> None:
        match operation:
            case AddTrack(track, state):
                self._insert_new_track(track)
                self._put_file_state(state)
            case UpdateTrack(track, state) | MoveTrack(track, state, _):
                self._replace_track(track)
                self._put_file_state(state)
            case MarkPresent(track_id, state) | RefreshState(track_id, state):
                self._require_track(track_id)
                self._put_file_state(state)
            case MarkMissing(track_id):
                self._require_track(track_id)
                cursor = self._db.execute(
                    "UPDATE file_state SET missing = 1 WHERE track_id = ?", (str(track_id),)
                )
                if cursor.rowcount == 0:
                    raise NotFoundError(f"track {track_id} has no file state")
            case RegisterSource(source, imported_at):
                self._db.execute(
                    "INSERT INTO sources (name, imported_at) VALUES (?, ?)"
                    " ON CONFLICT (name) DO UPDATE SET imported_at = excluded.imported_at",
                    (source, imported_at.isoformat()),
                )
            case AddImportedTrack(track, source, values):
                self._insert_new_track(track)
                self._put_source_values(source, track.id, values)
            case UpdateImportedTrack(track, source, values):
                self._replace_track(track)
                self._put_source_values(source, track.id, values)
            case RecordSourceValues(track_id, source, values):
                self._require_track(track_id)
                self._put_source_values(source, track_id, values)
            case ReplaceSourceFolder(source, folder):
                self._replace_source_folder(source, folder)

    def _insert_new_track(self, track: Track) -> None:
        self._check_path_free(track)
        try:
            self._insert_tracks([track])
        except sqlite3.IntegrityError as error:
            raise ConflictError(f"track {track.id} already exists") from error

    def _put_source_values(
        self, source: str, track_id: TrackId, values: Mapping[str, JSONValue]
    ) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO source_values (source, track_id, field_values)"
            " VALUES (?, ?, ?)",
            (source, str(track_id), json.dumps(values, ensure_ascii=False, allow_nan=False)),
        )

    def _replace_source_folder(self, source: str, folder: Folder) -> None:
        info = self.source(source)
        if info is None:
            raise NotFoundError(f"source {source!r} is not registered")
        if info.root_node_id is not None:
            if info.root_node_id != folder.id:
                raise ConflictError(f"the folder of source {source!r} has another id")
            self._replace_node(folder)
            return
        self._check_entries(folder)
        position = self._make_room(None, None)
        try:
            self._insert_nodes([(None, position, folder)])
        except sqlite3.IntegrityError as error:
            raise ConflictError(f"a node of {folder.name!r} already exists") from error
        self._db.execute(
            "UPDATE sources SET root_node_id = ? WHERE name = ?", (str(folder.id), source)
        )

    # Import sources

    def source(self, name: str) -> SourceInfo | None:
        row = self._db.execute(
            "SELECT root_node_id, imported_at FROM sources WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return SourceInfo(
            name=name,
            root_node_id=None if row[0] is None else NodeId(uuid.UUID(row[0])),
            imported_at=datetime.datetime.fromisoformat(row[1]),
        )

    def source_values(self, name: str) -> dict[TrackId, dict[str, JSONValue]]:
        """The merge base per track: what the last import from ``name`` read."""
        rows = self._db.execute(
            "SELECT track_id, field_values FROM source_values WHERE source = ?", (name,)
        ).fetchall()
        return {TrackId(uuid.UUID(track_id)): json.loads(values) for track_id, values in rows}

    def _require_track(self, track_id: TrackId) -> None:
        row = self._db.execute("SELECT 1 FROM tracks WHERE id = ?", (str(track_id),)).fetchone()
        if row is None:
            raise NotFoundError(f"track {track_id} does not exist")

    def _put_file_state(self, state: FileState) -> None:
        self._db.execute(
            f"INSERT OR REPLACE INTO file_state ({_FILE_STATE_COLUMNS})"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(state.track_id),
                state.size,
                state.mtime_ns,
                state.quick_hash,
                int(state.missing),
                state.scanned_at.isoformat(),
                json.dumps(state.scanned_values, ensure_ascii=False, allow_nan=False),
            ),
        )

    def delete_track(self, track_id: TrackId) -> None:
        """Delete a track; its entries disappear from every playlist."""
        with self._write():
            cursor = self._db.execute("DELETE FROM tracks WHERE id = ?", (str(track_id),))
            if cursor.rowcount == 0:
                raise NotFoundError(f"track {track_id} does not exist")
            self._delete_orphan_tags()

    # Playlist nodes

    def add_node(
        self, node: Node, parent_id: NodeId | None = None, index: int | None = None
    ) -> None:
        """Insert ``node`` (with its whole subtree) under a folder or at the root.

        ``index`` is the position among the parent's children; ``None`` appends.
        """
        with self._write():
            self._check_parent(parent_id)
            self._check_entries(node)
            position = self._make_room(parent_id, index)
            try:
                self._insert_nodes([(parent_id, position, node)])
            except sqlite3.IntegrityError as error:
                raise ConflictError(f"a node of {node.name!r} already exists") from error

    def get_node(self, node_id: NodeId) -> Node:
        """Return the node with its whole subtree."""
        forest = self._load_nodes(_SUBTREE, (str(node_id),))
        if not forest:
            raise NotFoundError(f"playlist node {node_id} does not exist")
        return forest[0]

    def children(self, parent_id: NodeId | None = None) -> tuple[Node, ...]:
        """Children of a folder, or the root nodes when ``parent_id`` is ``None``."""
        if parent_id is None:
            return self._load_nodes()
        node = self.get_node(parent_id)
        if not isinstance(node, Folder):
            raise ValidationError("Store", "parent_id", f"{node.name!r} is not a folder")
        return node.children

    def update_node(self, node: Node) -> None:
        """Replace the stored node with the same id, keeping its place in the tree.

        For folders, the stored subtree is replaced by ``node.children``.
        """
        with self._write():
            self._replace_node(node)

    def _replace_node(self, node: Node) -> None:
        row = self._db.execute(
            "SELECT parent_id, position FROM playlist_nodes WHERE id = ?", (str(node.id),)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"playlist node {node.id} does not exist")
        self._check_entries(node)
        parent_id = None if row[0] is None else NodeId(uuid.UUID(row[0]))
        # Deleting cascades to sync state; keep it for the nodes that remain.
        synced = self._db.execute(
            f"{_SUBTREE} SELECT target, node_id, fingerprint, synced_at, target_path"
            " FROM sync_state WHERE node_id IN (SELECT id FROM subtree)",
            (str(node.id),),
        ).fetchall()
        # The same goes for a source whose root folder is this node.
        roots = self._db.execute(
            "SELECT name FROM sources WHERE root_node_id = ?", (str(node.id),)
        ).fetchall()
        self._db.execute("DELETE FROM playlist_nodes WHERE id = ?", (str(node.id),))
        try:
            self._insert_nodes([(parent_id, row[1], node)])
        except sqlite3.IntegrityError as error:
            raise ConflictError(f"a node of {node.name!r} already exists") from error
        self._db.executemany(
            "INSERT INTO sync_state (target, node_id, fingerprint, synced_at, target_path)"
            " SELECT ?, ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM playlist_nodes WHERE id = ?)",
            ((*synced_row, synced_row[1]) for synced_row in synced),
        )
        self._db.executemany(
            "UPDATE sources SET root_node_id = ? WHERE name = ?",
            ((str(node.id), name) for (name,) in roots),
        )

    def delete_node(self, node_id: NodeId) -> None:
        """Delete a node; deleting a folder deletes everything below it."""
        with self._write():
            cursor = self._db.execute("DELETE FROM playlist_nodes WHERE id = ?", (str(node_id),))
            if cursor.rowcount == 0:
                raise NotFoundError(f"playlist node {node_id} does not exist")

    # Export sync state (not library content: the revision is left unchanged)

    def sync_state(self, target: str) -> dict[NodeId, str]:
        """Fingerprints of the nodes last exported to ``target``."""
        rows = self._db.execute(
            "SELECT node_id, fingerprint FROM sync_state WHERE target = ?", (target,)
        ).fetchall()
        return {NodeId(uuid.UUID(node_id)): fingerprint for node_id, fingerprint in rows}

    def sync_paths(self, target: str) -> dict[NodeId, tuple[str, ...]]:
        """Where ``target`` holds each node exported to it, for targets that record it."""
        rows = self._db.execute(
            "SELECT node_id, target_path FROM sync_state"
            " WHERE target = ? AND target_path IS NOT NULL",
            (target,),
        ).fetchall()
        return {NodeId(uuid.UUID(node_id)): tuple(json.loads(path)) for node_id, path in rows}

    def record_sync(
        self,
        target: str,
        fingerprints: Mapping[NodeId, str],
        at: datetime.datetime,
        *,
        target_paths: Mapping[NodeId, Sequence[str]] | None = None,
        source_values: Mapping[TrackId, Mapping[str, JSONValue]] | None = None,
    ) -> None:
        """Record what was exported of each node to ``target``, replacing earlier entries.

        ``source_values`` become the merge base of those tracks for ``target``, which is
        registered as a source when it is not one yet.
        """
        paths = target_paths or {}
        with transaction(self._db):
            self._db.executemany(
                "INSERT OR REPLACE INTO sync_state"
                " (target, node_id, fingerprint, synced_at, target_path) VALUES (?, ?, ?, ?, ?)",
                (
                    (
                        target,
                        str(node_id),
                        fp,
                        at.isoformat(),
                        json.dumps(list(paths[node_id]), ensure_ascii=False)
                        if node_id in paths
                        else None,
                    )
                    for node_id, fp in fingerprints.items()
                ),
            )
            if source_values:
                self._db.execute(
                    "INSERT INTO sources (name, imported_at) VALUES (?, ?)"
                    " ON CONFLICT (name) DO NOTHING",
                    (target, at.isoformat()),
                )
                for track_id, values in source_values.items():
                    self._require_track(track_id)
                    self._put_source_values(target, track_id, values)

    # Whole library

    def replace_library(self, library: Library) -> None:
        """Make the stored library equal to ``library``."""
        with self._write():
            self._db.execute("DELETE FROM playlist_nodes")
            self._db.execute("DELETE FROM tracks")
            self._db.execute("DELETE FROM tags")
            self._insert_tracks(library.tracks.values())
            self._insert_nodes((None, i, root) for i, root in enumerate(library.playlists))

    def load_library(self) -> Library:
        return Library.build(self._load_tracks(), self._load_nodes())

    # Writing helpers

    def _check_path_free(self, track: Track) -> None:
        row = self._db.execute(
            "SELECT id FROM tracks WHERE path = ? AND id <> ?", (track.path, str(track.id))
        ).fetchone()
        if row is not None:
            raise ConflictError(f"another track already has the path {track.path!r}")

    def _insert_tracks(self, tracks: Iterable[Track]) -> None:
        tracks = list(tracks)
        self._db.executemany(_TRACK_INSERT, (_track_row(t) for t in tracks))
        self._insert_track_children(tracks)

    def _insert_track_children(self, tracks: Sequence[Track]) -> None:
        self._db.executemany(
            "INSERT INTO cues (track_id, position, kind, start_us, slot, name, color, end_us,"
            " active, unmapped) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (str(t.id), i, c.kind.value, c.start_us, c.slot, c.name, c.color, c.end_us,
                 int(c.active), _dump_unmapped(c.unmapped))
                for t in tracks
                for i, c in enumerate(t.cues)
            ),
        )  # fmt: skip
        self._db.executemany(
            "INSERT INTO beat_markers (track_id, position, position_us, bpm, beat)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                (str(t.id), i, m.position_us, m.bpm, m.beat)
                for t in tracks
                if t.beatgrid is not None
                for i, m in enumerate(t.beatgrid.markers)
            ),
        )
        names = {tag for t in tracks for tag in t.tags}
        self._db.executemany("INSERT OR IGNORE INTO tags (name) VALUES (?)", ((n,) for n in names))
        tag_ids = dict(self._db.execute("SELECT name, id FROM tags").fetchall()) if names else {}
        self._db.executemany(
            "INSERT INTO track_tags (track_id, position, tag_id) VALUES (?, ?, ?)",
            ((str(t.id), i, tag_ids[tag]) for t in tracks for i, tag in enumerate(t.tags)),
        )

    def _delete_orphan_tags(self) -> None:
        self._db.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM track_tags)")

    def _check_parent(self, parent_id: NodeId | None) -> None:
        if parent_id is None:
            return
        row = self._db.execute(
            "SELECT kind, name FROM playlist_nodes WHERE id = ?", (str(parent_id),)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"playlist node {parent_id} does not exist")
        if row[0] != "folder":
            raise ValidationError("Store", "parent_id", f"{row[1]!r} is a {row[0]}, not a folder")

    def _check_entries(self, node: Node) -> None:
        wanted = {
            str(entry) for n in _subtree(node) if isinstance(n, Playlist) for entry in n.entries
        }
        if not wanted:
            return
        known = {
            row[0]
            for row in self._db.execute(
                "SELECT value FROM json_each(?) WHERE value IN (SELECT id FROM tracks)",
                (json.dumps(sorted(wanted)),),
            )
        }
        missing = wanted - known
        if missing:
            raise ValidationError("Store", "entries", f"unknown track {min(missing)}")

    def _make_room(self, parent_id: NodeId | None, index: int | None) -> int:
        """Return the position for a new child at ``index``, shifting later siblings."""
        if index is not None and index < 0:
            raise ValidationError("Store", "index", "must not be negative")
        parent = None if parent_id is None else str(parent_id)
        positions = [
            row[0]
            for row in self._db.execute(
                "SELECT position FROM playlist_nodes WHERE parent_id IS ? ORDER BY position",
                (parent,),
            )
        ]
        if index is None or index >= len(positions):
            return positions[-1] + 1 if positions else 0
        position = positions[index]
        # Two steps so the unique (parent, position) index never sees a duplicate.
        self._db.execute(
            "UPDATE playlist_nodes SET position = -position - 1"
            " WHERE parent_id IS ? AND position >= ?",
            (parent, position),
        )
        self._db.execute(
            "UPDATE playlist_nodes SET position = -position WHERE parent_id IS ? AND position < 0",
            (parent,),
        )
        return position

    def _insert_nodes(self, nodes: Iterable[tuple[NodeId | None, int, Node]]) -> None:
        """Insert ``(parent id, position, node)`` triples; subtrees of folders included."""
        node_rows: list[Row] = []
        entry_rows: list[Row] = []
        rule_rows: list[Row] = []
        for parent_id, position, root in nodes:
            stack = [(parent_id, position, root)]
            while stack:
                parent, index, node = stack.pop()
                match_mode = node.match.value if isinstance(node, Smartlist) else None
                node_rows.append(
                    (str(node.id), None if parent is None else str(parent), index,
                     _node_kind(node), node.name, match_mode, _dump_unmapped(node.unmapped))
                )  # fmt: skip
                if isinstance(node, Folder):
                    stack.extend((node.id, i, child) for i, child in enumerate(node.children))
                elif isinstance(node, Playlist):
                    entry_rows.extend((str(node.id), i, str(e)) for i, e in enumerate(node.entries))
                else:
                    rule_rows.extend(
                        (str(node.id), i, r.field, r.operator, json.dumps(list(r.values)))
                        for i, r in enumerate(node.rules)
                    )
        # Parents are queued before their children, so foreign keys hold row by row.
        self._db.executemany(
            f"INSERT INTO playlist_nodes ({_NODE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)", node_rows
        )
        self._db.executemany(
            "INSERT INTO playlist_entries (node_id, position, track_id) VALUES (?, ?, ?)",
            entry_rows,
        )
        self._db.executemany(
            "INSERT INTO smartlist_rules (node_id, position, field, operator, values_json)"
            " VALUES (?, ?, ?, ?, ?)",
            rule_rows,
        )

    # Reading helpers

    def _load_tracks(self, where: str = "", params: Sequence[object] = ()) -> list[Track]:
        rows = self._db.execute(f"{_TRACK_SELECT} {where} ORDER BY path", params).fetchall()
        if not rows:
            return []
        scope = f"WHERE track_id IN (SELECT id FROM tracks {where})" if where else ""
        cues: defaultdict[str, list[Cue]] = defaultdict(list)
        for track_id, kind, start, slot, name, color, end, active, unmapped in self._db.execute(
            "SELECT track_id, kind, start_us, slot, name, color, end_us, active, unmapped"
            f" FROM cues {scope} ORDER BY track_id, position",
            params,
        ):
            cues[track_id].append(
                Cue(kind=CueKind(kind), start_us=start, slot=slot, name=name, color=color,
                    end_us=end, active=bool(active), unmapped=_load_unmapped(unmapped))
            )  # fmt: skip
        markers: defaultdict[str, list[BeatMarker]] = defaultdict(list)
        for track_id, position_us, bpm, beat in self._db.execute(
            f"SELECT track_id, position_us, bpm, beat FROM beat_markers {scope}"
            " ORDER BY track_id, position",
            params,
        ):
            markers[track_id].append(BeatMarker(position_us=position_us, bpm=bpm, beat=beat))
        tags: defaultdict[str, list[str]] = defaultdict(list)
        for track_id, name in self._db.execute(
            "SELECT track_id, name FROM track_tags JOIN tags ON tags.id = track_tags.tag_id"
            f" {scope} ORDER BY track_id, position",
            params,
        ):
            tags[track_id].append(name)
        return [_track_from_row(row, cues, markers, tags) for row in rows]

    def _load_nodes(
        self, subtree: str | None = None, params: Sequence[object] = ()
    ) -> tuple[Node, ...]:
        """Load the whole forest, or one subtree when ``subtree`` is the recursive CTE."""
        prefix, scope = (
            (subtree, "WHERE node_id IN (SELECT id FROM subtree)") if subtree else ("", "")
        )
        node_scope = "WHERE id IN (SELECT id FROM subtree)" if subtree else ""
        rows = self._db.execute(
            f"{prefix} SELECT {_NODE_COLUMNS} FROM playlist_nodes {node_scope}"
            " ORDER BY parent_id, position",
            params,
        ).fetchall()
        entries: defaultdict[str, list[TrackId]] = defaultdict(list)
        for node_id, track_id in self._db.execute(
            f"{prefix} SELECT node_id, track_id FROM playlist_entries {scope}"
            " ORDER BY node_id, position",
            params,
        ):
            entries[node_id].append(TrackId(uuid.UUID(track_id)))
        rules: defaultdict[str, list[Rule]] = defaultdict(list)
        for node_id, field, operator, values in self._db.execute(
            f"{prefix} SELECT node_id, field, operator, values_json FROM smartlist_rules {scope}"
            " ORDER BY node_id, position",
            params,
        ):
            rule = Rule(field=field, operator=operator, values=tuple(json.loads(values)))
            rules[node_id].append(rule)

        children: defaultdict[str | None, list[Row]] = defaultdict(list)
        for row in rows:
            children[row[1]].append(row)
        ids = {row[0] for row in rows}
        roots = [row for row in rows if row[1] is None or row[1] not in ids]

        def build(row: Row) -> Node:
            node_id, _parent, _position, kind, name, match_mode, unmapped = row
            common: dict[str, Any] = {
                "id": NodeId(uuid.UUID(node_id)),
                "name": name,
                "unmapped": _load_unmapped(unmapped),
            }
            if kind == "folder":
                return Folder(children=tuple(build(c) for c in children[node_id]), **common)
            if kind == "playlist":
                return Playlist(entries=tuple(entries[node_id]), **common)
            return Smartlist(match=MatchMode(match_mode), rules=tuple(rules[node_id]), **common)

        return tuple(build(row) for row in sorted(roots, key=lambda r: r[2]))


def _subtree(node: Node) -> list[Node]:
    """The node and all of its descendants."""
    nodes = [node]
    for current in nodes:
        if isinstance(current, Folder):
            nodes.extend(current.children)
    return nodes


def _file_state_from_row(row: Row) -> FileState:
    track_id, size, mtime_ns, quick_hash, missing, scanned_at, scanned_values = row
    return FileState(
        track_id=TrackId(uuid.UUID(track_id)),
        size=size,
        mtime_ns=mtime_ns,
        quick_hash=quick_hash,
        missing=bool(missing),
        scanned_at=datetime.datetime.fromisoformat(scanned_at),
        scanned_values=json.loads(scanned_values),
    )


def _node_kind(node: Node) -> str:
    if isinstance(node, Folder):
        return "folder"
    return "playlist" if isinstance(node, Playlist) else "smartlist"


def _dump_unmapped(unmapped: Mapping[str, JSONValue]) -> str | None:
    return json.dumps(unmapped, ensure_ascii=False, allow_nan=False) if unmapped else None


def _load_unmapped(text: str | None) -> dict[str, JSONValue]:
    return json.loads(text) if text else {}


def _track_row(track: Track) -> Row:
    return (
        str(track.id),
        track.path,
        track.path_origin,
        *(getattr(track, name) for name in _PLAIN_FIELDS),
        None if track.key is None else track.key.code,
        *(_iso(getattr(track, name)) for name in DATE_FIELDS),
        _iso(track.last_played),
        _dump_unmapped(track.unmapped),
    )


def _iso(value: datetime.date | None) -> str | None:
    return None if value is None else value.isoformat()


def _track_from_row(
    row: Row,
    cues: Mapping[str, list[Cue]],
    markers: Mapping[str, list[BeatMarker]],
    tags: Mapping[str, list[str]],
) -> Track:
    values = dict(zip(_TRACK_COLUMNS, row, strict=True))
    track_id: str = values["id"]
    key_code: int | None = values["key_code"]
    last_played: str | None = values["last_played"]
    grid = markers.get(track_id)
    fields: dict[str, Any] = {name: values[name] for name in _PLAIN_FIELDS}
    for name in DATE_FIELDS:
        fields[name] = None if values[name] is None else datetime.date.fromisoformat(values[name])
    return Track(
        id=TrackId(uuid.UUID(track_id)),
        path_origin=values["path_origin"],
        key=None if key_code is None else Key.from_code(key_code),
        last_played=None if last_played is None else datetime.datetime.fromisoformat(last_played),
        tags=tuple(tags.get(track_id, ())),
        cues=tuple(cues.get(track_id, ())),
        beatgrid=None if grid is None else BeatGrid(markers=tuple(grid)),
        unmapped=_load_unmapped(values["unmapped"]),
        **fields,
    )
