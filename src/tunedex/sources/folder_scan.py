"""Scanning music folders into scan plans.

A scan reads files and the store but changes neither: it returns a ``ScanPlan``,
applied with ``Store.apply_scan``. Files whose size and modification time are
unchanged since the last scan are not opened.
"""

import dataclasses
import datetime
import hashlib
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tunedex.model.errors import ValidationError
from tunedex.model.ids import TrackId
from tunedex.model.key import Key
from tunedex.model.paths import normalize_path
from tunedex.model.track import Track
from tunedex.model.unmapped import JSONValue
from tunedex.sources.merge import merge_fields
from tunedex.sources.scan_plan import (
    AddTrack,
    Conflict,
    MarkMissing,
    MarkPresent,
    MoveTrack,
    RefreshState,
    ScanOperation,
    ScanPlan,
    UpdateTrack,
)
from tunedex.sources.tags import SCANNED_FIELDS, read_file
from tunedex.store import FileState, Store

AUDIO_EXTENSIONS = frozenset({".mp3", ".flac", ".wav", ".aif", ".aiff", ".m4a", ".ogg"})
_EDGE = 16 * 1024


@dataclass(frozen=True, slots=True)
class _Found:
    path: Path
    normalized: str
    size: int
    mtime_ns: int


_PROGRESS_EVERY = 250


def quick_hash(path: Path, size: int) -> str:
    """SHA-256 of the size and the first and last 16 KiB (the whole file if smaller)."""
    digest = hashlib.sha256(size.to_bytes(8, "big"))
    with path.open("rb") as file:
        if size <= 2 * _EDGE:
            digest.update(file.read())
        else:
            digest.update(file.read(_EDGE))
            file.seek(-_EDGE, os.SEEK_END)
            digest.update(file.read(_EDGE))
    return digest.hexdigest()


def discover(
    root: Path, warnings: list[str], *, progress: Callable[[int], None] | None = None
) -> Iterator[_Found]:
    """Audio files under ``root``, depth first and sorted by name.

    ``progress`` is told the number of files found every 250 files and at the end.
    """
    if progress is None:
        yield from _walk(root, warnings, set())
        return
    count = 0
    for count, found in enumerate(_walk(root, warnings, set()), start=1):
        if count % _PROGRESS_EVERY == 0:
            progress(count)
        yield found
    progress(count)


def _walk(root: Path, warnings: list[str], seen: set[str]) -> Iterator[_Found]:
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError as error:
        warnings.append(f"{root}: cannot list directory ({error})")
        return
    for entry in entries:
        name = entry.name
        if name.startswith("."):
            continue
        if not _is_utf8(name):
            shown = os.fsencode(entry.path).decode("utf-8", errors="backslashreplace")
            warnings.append(f"skipped {shown}: the name is not valid UTF-8; rename it to scan it")
            continue
        path = Path(entry.path)
        try:
            if entry.is_dir(follow_symlinks=False):
                yield from _walk(path, warnings, seen)
            elif path.suffix.lower() in AUDIO_EXTENSIONS and entry.is_file():
                normalized = normalize_path(str(path))
                if normalized in seen:  # the same name in another Unicode form
                    warnings.append(
                        f"skipped {path}: another file has the same name in a different "
                        "Unicode form; rename it to scan it"
                    )
                    continue
                seen.add(normalized)
                stat = entry.stat()
                yield _Found(path, normalized, stat.st_size, stat.st_mtime_ns)
        except OSError as error:
            warnings.append(f"{path}: cannot read ({error})")


def _is_utf8(name: str) -> bool:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


@dataclass
class _Scan:
    store: Store
    root: Path
    now: datetime.datetime
    progress: Callable[[int], None] | None = None
    warnings: list[str] = field(default_factory=list[str])
    conflicts: list[Conflict] = field(default_factory=list[Conflict])

    def run(self) -> ScanPlan:
        root = normalize_path(str(self.root))
        known = {t.path: t for t in self.store.list_tracks_under(root)}
        states = self.store.file_states(root)
        merged_away = self.store.merged_paths()

        moves: list[ScanOperation] = []
        changes: list[ScanOperation] = []
        adds: list[ScanOperation] = []
        missing: list[ScanOperation] = []
        seen: set[str] = set()
        unknown: list[_Found] = []

        for found in discover(self.root, self.warnings, progress=self.progress):
            track = known.get(found.normalized)
            if track is None:
                if found.normalized not in merged_away:  # a merged duplicate kept on disk
                    unknown.append(found)
                continue
            seen.add(found.normalized)
            state = states.get(track.id)
            if state is not None and (state.size, state.mtime_ns) == (found.size, found.mtime_ns):
                if state.missing:
                    present = dataclasses.replace(state, missing=False, scanned_at=self.now)
                    changes.append(MarkPresent(track.id, present))
                continue
            merged, new_state = self._reread(track, state, found)
            if merged != track:
                changes.append(UpdateTrack(merged, new_state))
            else:
                changes.append(RefreshState(track.id, new_state))

        vanished = [t for path, t in known.items() if path not in seen]
        candidates: dict[tuple[int, str], list[Track]] = {}
        for track in vanished:
            state = states.get(track.id)
            if state is not None:
                candidates.setdefault((state.size, state.quick_hash), []).append(track)

        moved: set[TrackId] = set()
        for found in unknown:
            digest = quick_hash(found.path, found.size)
            matches = [t for t in candidates.get((found.size, digest), []) if t.id not in moved]
            if len(matches) == 1:
                (track,) = matches
                relocated = dataclasses.replace(track, path_origin=os.fspath(found.path))
                merged, new_state = self._reread(relocated, states.get(track.id), found, digest)
                moves.append(MoveTrack(merged, new_state, old_path=track.path))
                moved.add(track.id)
                continue
            if len(matches) > 1:
                names = ", ".join(t.path for t in matches)
                self.warnings.append(
                    f"{found.path}: matches several missing tracks ({names}); added as new"
                )
            adds.append(self._new_track(found, digest))

        for track in vanished:
            state = states.get(track.id)
            if track.id not in moved and state is not None and not state.missing:
                missing.append(MarkMissing(track.id))

        return ScanPlan(
            root=self.root,
            operations=(*moves, *changes, *adds, *missing),
            conflicts=tuple(self.conflicts),
            warnings=tuple(self.warnings),
        )

    def _new_track(self, found: _Found, digest: str) -> AddTrack:
        read = read_file(found.path)
        self.warnings.extend(read.warnings)
        values = dict(read.values)
        modified = datetime.datetime.fromtimestamp(found.mtime_ns / 1e9, datetime.UTC).date()
        track = self._build(
            lambda v: Track(
                path_origin=os.fspath(found.path),
                date_added=self.now.date(),
                date_modified=modified,
                **v,
            ),
            values,
            found.path,
        )
        return AddTrack(track, self._state(track.id, found, digest, read.values))

    def _reread(
        self, track: Track, state: FileState | None, found: _Found, digest: str | None = None
    ) -> tuple[Track, FileState]:
        read = read_file(found.path)
        self.warnings.extend(read.warnings)
        base = None if state is None else state.scanned_values
        changes = self._merge(track, base, read.values)
        merged = self._build(lambda v: dataclasses.replace(track, **v), changes, found.path)
        digest = digest or quick_hash(found.path, found.size)
        return merged, self._state(track.id, found, digest, read.values)

    def _merge(
        self, track: Track, base: Mapping[str, JSONValue] | None, theirs: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Field changes from a three-way merge of the last scan, the library and the file."""
        changes, disagreements = merge_fields(track, base, theirs, SCANNED_FIELDS, _encode)
        self.conflicts.extend(
            Conflict(track.id, d.field, d.library_value, d.source_value) for d in disagreements
        )
        return changes

    def _build(
        self, make: Callable[[dict[str, Any]], Track], values: dict[str, Any], path: Path
    ) -> Track:
        """Build a track, dropping (with a warning) any value the model rejects."""
        values = dict(values)
        while True:
            try:
                return make(values)
            except ValidationError as error:
                if error.field not in values:
                    raise
                self.warnings.append(f"{path}: ignored invalid {error.field} ({error.message})")
                del values[error.field]

    def _state(
        self, track_id: TrackId, found: _Found, digest: str, values: Mapping[str, Any]
    ) -> FileState:
        return FileState(
            track_id=track_id,
            size=found.size,
            mtime_ns=found.mtime_ns,
            quick_hash=digest,
            scanned_at=self.now,
            missing=False,
            scanned_values=encode_values(values),
        )


def encode_values(values: Mapping[str, Any]) -> dict[str, JSONValue]:
    """Scanned field values as JSON (keys as their canonical codes)."""
    return {name: _encode(name, values.get(name)) for name in SCANNED_FIELDS}


def _encode(name: str, value: Any) -> JSONValue:
    return value.code if isinstance(value, Key) else value


def scan_folder(
    store: Store,
    root: str | os.PathLike[str],
    *,
    clock: Callable[[], datetime.datetime] | None = None,
    progress: Callable[[Path, int], None] | None = None,
) -> ScanPlan:
    """Scan ``root`` against the tracks of ``store`` below it. Changes nothing.

    ``progress`` is told the root and how many audio files were found so far.
    """
    now = (clock or (lambda: datetime.datetime.now(datetime.UTC)))()
    folder = Path(root).absolute()
    count: Callable[[int], None] | None = None
    if progress is not None:
        report = progress

        def tell(seen: int) -> None:
            report(folder, seen)

        count = tell
    return _Scan(store, folder, now, count).run()
