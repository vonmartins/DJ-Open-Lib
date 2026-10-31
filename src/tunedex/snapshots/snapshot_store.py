"""Creating, listing, restoring and pruning snapshots on disk."""

import datetime
import hashlib
import os
import re
import secrets
import shutil
import sqlite3
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from tunedex.snapshots.errors import RestoreError, SnapshotCorruptError, SnapshotError
from tunedex.snapshots.manifest import (
    CopyMethod,
    FileRecord,
    Rename,
    Snapshot,
    TagBytes,
    dump_manifest,
    load_manifest,
)
from tunedex.snapshots.moves import move_file, name_free
from tunedex.tagwrite.regions import LayoutError, audio_region, audio_sha256, copy_range

DEFAULT_KEEP = 10
MANIFEST = "manifest.json"
_TARGET_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SNAPSHOT_DIR = re.compile(r"^(\d{6,})-\d{8}T\d{6}Z$")
_TEMPORARY_PREFIX = ".tmp-"
_SQLITE_HEADER = b"SQLite format 3\x00"
# ``SnapshotStore.list`` shadows the builtin inside the class body.
_SnapshotIds = list[str]


@dataclass(frozen=True, slots=True)
class RestoreResult:
    restored: Snapshot
    pre_restore: Snapshot


class SnapshotStore:
    """Snapshots of named targets kept under ``root``, at most ``keep`` per target."""

    def __init__(
        self,
        root: Path,
        *,
        keep: int = DEFAULT_KEEP,
        _clock: Callable[[], datetime.datetime] | None = None,
        _version: str | None = None,
    ) -> None:
        if type(keep) is not int or keep < 1:
            raise ValueError(f"keep must be an integer of at least 1, got {keep!r}")
        self.root = root
        self.keep = keep
        self._clock = _clock or (lambda: datetime.datetime.now(datetime.UTC))
        self._version = _version

    # Creating

    def create(
        self,
        target: str,
        files: Iterable[Path],
        *,
        reason: str | None = None,
        exact: bool = False,
        renames: Iterable[Rename] = (),
    ) -> Snapshot:
        """Copy ``files`` (absolute paths; missing ones are recorded as absent).

        SQLite databases are copied through SQLite, which is safe while they are open.
        ``exact`` copies every file byte for byte instead, for callers that already
        made sure nothing writes to them and need the copies to match their hashes.
        ``renames`` are recorded with the copies: restoring the snapshot renames each
        file back to its old name before putting the copies back.
        """
        return self._create(
            target,
            _check_files(files),
            reason=reason,
            protect=(),
            exact=exact,
            renames=tuple(renames),
        )

    def create_tags(
        self, target: str, files: Iterable[Path], *, reason: str | None = None
    ) -> Snapshot:
        """Copy the tags of the audio files ``files``: every byte outside the audio stream.

        The audio stream is not copied; its hash is recorded, and restoring rebuilds
        each file from the copy and the audio stream it has then.
        """
        return self._create(target, _check_files(files), reason=reason, protect=(), tags=True)

    def _create(
        self,
        target: str,
        paths: list[Path],
        *,
        reason: str | None,
        protect: Collection[str],
        exact: bool = False,
        tags: bool = False,
        renames: tuple[Rename, ...] = (),
    ) -> Snapshot:
        directory = self._target_dir(target)
        directory.mkdir(parents=True, exist_ok=True)
        _remove_temporary(directory)

        sequence = max((s.sequence for s in self.list(target)), default=0) + 1
        created_at = self._clock()
        snapshot_id = f"{sequence:06d}-{created_at:%Y%m%dT%H%M%SZ}"
        temporary = directory / f"{_TEMPORARY_PREFIX}{snapshot_id}"
        try:
            (temporary / "files").mkdir(parents=True)
            records = tuple(
                _copy_tags_in(path, temporary / "files" / str(index))
                if tags
                else _copy_in(path, temporary / "files" / str(index), exact=exact)
                for index, path in enumerate(paths)
            )
            snapshot = Snapshot(
                id=snapshot_id,
                target=target,
                created_at=created_at,
                tunedex_version=self._version or version("tunedex"),
                reason=reason,
                files=records,
                renames=renames,
            )
            _write_synced(temporary / MANIFEST, dump_manifest(snapshot).encode("utf-8"))
            temporary.rename(directory / snapshot_id)
        except (OSError, sqlite3.Error, LayoutError) as error:
            shutil.rmtree(temporary, ignore_errors=True)
            raise SnapshotError(f"cannot snapshot target {target!r}: {error}") from error

        self.prune(target, protect=protect)
        return snapshot

    # Listing

    def targets(self) -> _SnapshotIds:
        """Names of the targets that have a snapshot directory, sorted."""
        if not self.root.is_dir():
            return []
        return sorted(
            entry.name
            for entry in self.root.iterdir()
            if entry.is_dir() and _TARGET_NAME.match(entry.name)
        )

    def list(self, target: str) -> list[Snapshot]:
        """Snapshots of ``target``, newest first. Unreadable directories are skipped."""
        directory = self._target_dir(target)
        if not directory.is_dir():
            return []
        snapshots: list[Snapshot] = []
        for entry in directory.iterdir():
            if not _SNAPSHOT_DIR.match(entry.name):
                continue
            try:
                snapshot = load_manifest((entry / MANIFEST).read_text(encoding="utf-8"))
            except (OSError, SnapshotCorruptError):
                continue
            if snapshot.id == entry.name and snapshot.target == target:
                snapshots.append(snapshot)
        return sorted(snapshots, key=lambda s: s.sequence, reverse=True)

    def get(self, target: str, snapshot_id: str) -> Snapshot:
        for snapshot in self.list(target):
            if snapshot.id == snapshot_id:
                return snapshot
        raise SnapshotError(f"snapshot {snapshot_id!r} of target {target!r} does not exist")

    # Restoring

    def verify(self, snapshot: Snapshot) -> None:
        """Check every copy against its manifest entry; raise ``SnapshotCorruptError`` if not."""
        files = self._snapshot_dir(snapshot) / "files"
        for index, record in enumerate(snapshot.files):
            if not record.present:
                continue
            copy = files / str(index)
            if not copy.is_file():
                raise SnapshotCorruptError(f"{record.path}: copy is missing from the snapshot")
            if copy.stat().st_size != record.copy_size or _sha256(copy) != record.copy_sha256:
                raise SnapshotCorruptError(f"{record.path}: copy does not match the manifest")

    def restore(self, snapshot: Snapshot) -> RestoreResult:
        """Put every target file back to the state recorded in ``snapshot``.

        Recorded renames are undone first. The current state is snapshotted first.
        Databases must not be open in any store while they are restored. Tag snapshots
        are restored only when every file still has the audio stream they recorded.
        """
        self.verify(snapshot)
        for record in snapshot.files:
            if record.method == "sqlite":
                for suffix in ("-journal", "-wal"):
                    if Path(record.path + suffix).exists():
                        raise SnapshotError(
                            f"{record.path}{suffix} exists; close every program using the"
                            " database before restoring it"
                        )

        _check_restorable(snapshot)

        paths = [Path(record.path) for record in snapshot.files]
        pre_restore = self._create(
            snapshot.target,
            paths,
            reason="pre-restore",
            protect={snapshot.id},
            tags=any(record.tags is not None for record in snapshot.files),
            renames=tuple(Rename(old=r.new, new=r.old) for r in reversed(snapshot.renames)),
        )
        try:
            self._apply(snapshot)
        except (OSError, SnapshotError, LayoutError) as error:
            try:
                self._apply(pre_restore)
            except (OSError, SnapshotError, LayoutError) as rollback_error:
                raise RestoreError(
                    f"restoring {snapshot.id} failed ({error}) and putting back the previous"
                    f" state also failed ({rollback_error}); the previous state is in snapshot"
                    f" {pre_restore.id}",
                    rolled_back=False,
                ) from error
            raise RestoreError(
                f"restoring {snapshot.id} failed ({error}); the previous state was put back",
                rolled_back=True,
            ) from error
        return RestoreResult(restored=snapshot, pre_restore=pre_restore)

    def restore_files(self, snapshot: Snapshot, paths: Collection[str]) -> None:
        """Put back only the files at ``paths``, without a pre-restore snapshot.

        For undoing a write that failed halfway, where only those files changed.
        """
        self.verify(snapshot)
        records = [r for r in snapshot.files if r.path in paths]
        self._put_back(snapshot, records)

    def _apply(self, snapshot: Snapshot) -> None:
        for rename in reversed(snapshot.renames):
            _undo_rename(rename)
        self._put_back(snapshot, snapshot.files)

    def _put_back(self, snapshot: Snapshot, records: Iterable[FileRecord]) -> None:
        records = list(records)
        files = self._snapshot_dir(snapshot) / "files"
        index_of = {record.path: index for index, record in enumerate(snapshot.files)}
        for record in records:
            target = Path(record.path)
            copy = files / str(index_of[record.path])
            if record.tags is not None:
                _rebuild(copy, target, record)
            elif record.present:
                _replace_file(copy, target, record.sha256 or "")
            else:
                target.unlink(missing_ok=True)
        for record in records:
            target = Path(record.path)
            if record.present and (not target.is_file() or _sha256(target) != record.sha256):
                raise SnapshotError(f"{record.path}: does not match the snapshot after restoring")
            if not record.present and target.exists():
                raise SnapshotError(f"{record.path}: still exists after restoring")

    # Retention

    def prune(self, target: str, *, protect: Collection[str] = ()) -> _SnapshotIds:
        """Delete snapshots of ``target`` beyond the newest ``keep``; return their ids."""
        deleted: _SnapshotIds = []
        for snapshot in self.list(target)[self.keep :]:
            if snapshot.id in protect:
                continue
            directory = self._snapshot_dir(snapshot)
            doomed = directory.with_name(f"{_TEMPORARY_PREFIX}delete-{snapshot.id}")
            directory.rename(doomed)
            shutil.rmtree(doomed, ignore_errors=True)
            deleted.append(snapshot.id)
        return deleted

    # Paths

    def _target_dir(self, target: str) -> Path:
        if not isinstance(target, str) or not _TARGET_NAME.match(target):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError(
                f"target names must match {_TARGET_NAME.pattern} (lower case), got {target!r}"
            )
        return self.root / target

    def _snapshot_dir(self, snapshot: Snapshot) -> Path:
        return self._target_dir(snapshot.target) / snapshot.id


def _check_files(files: Iterable[Path]) -> list[Path]:
    paths = [Path(f) for f in files]
    if not paths:
        raise ValueError("a target needs at least one file")
    seen: set[Path] = set()
    for path in paths:
        if not path.is_absolute():
            raise ValueError(f"target files must be absolute paths, got {path}")
        if path in seen:
            raise ValueError(f"{path} is listed twice")
        if path.is_dir():
            raise ValueError(f"{path} is a directory; targets are lists of files")
        seen.add(path)
    return paths


def _copy_in(source: Path, copy: Path, *, exact: bool = False) -> FileRecord:
    if not source.exists():
        return FileRecord(path=os.fspath(source), present=False)
    method: CopyMethod = "copy"
    if not exact and _is_sqlite(source):
        try:
            _sqlite_backup(source, copy)
            method = "sqlite"
        except sqlite3.DatabaseError:
            copy.unlink(missing_ok=True)
    if method == "copy":
        shutil.copyfile(source, copy)
    _fsync(copy)
    return FileRecord(
        path=os.fspath(source),
        present=True,
        size=copy.stat().st_size,
        sha256=_sha256(copy),
        method=method,
    )


def _copy_tags_in(source: Path, copy: Path) -> FileRecord:
    if not source.is_file():
        raise SnapshotError(f"{source}: the file is missing")
    region = audio_region(source)
    whole, audio, kept = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()

    with source.open("rb") as file, copy.open("wb") as out:

        def tag_bytes(data: bytes) -> None:
            whole.update(data)
            kept.update(data)
            out.write(data)

        def audio_bytes(data: bytes) -> None:
            whole.update(data)
            audio.update(data)

        copy_range(file, 0, region.start, tag_bytes)
        copy_range(file, region.start, region.end, audio_bytes)
        copy_range(file, region.end, region.size, tag_bytes)
        if file.read(1):
            raise SnapshotError(f"{source}: the file grew while its tags were copied")
    _fsync(copy)
    return FileRecord(
        path=os.fspath(source),
        present=True,
        size=region.size,
        sha256=whole.hexdigest(),
        method="tags",
        tags=TagBytes(
            audio_start=region.start,
            audio_end=region.end,
            audio_sha256=audio.hexdigest(),
            copy_sha256=kept.hexdigest(),
        ),
    )


def _check_restorable(snapshot: Snapshot) -> None:
    """Refuse, naming the files, when any file cannot be put back."""
    problems: list[str] = []
    for record in snapshot.files:
        if record.tags is None:
            continue
        target = Path(record.path)
        try:
            same = audio_sha256(target, audio_region(target)) == record.tags.audio_sha256
        except (OSError, LayoutError):
            same = False
        if not same:
            problems.append(f"{record.path} (missing, or its audio changed)")
    for rename in snapshot.renames:
        old, new = Path(rename.old), Path(rename.new)
        if not new.is_file():
            problems.append(f"{rename.new} (missing)")
        elif not name_free(new, old):
            problems.append(f"{rename.old} (another file has this name now)")
    if problems:
        raise SnapshotError(
            f"cannot restore snapshot {snapshot.id}; nothing was changed. Files: "
            + "; ".join(problems)
        )


def _undo_rename(rename: Rename) -> None:
    """Give ``rename.new`` its old name back; already done is fine, for rollbacks."""
    old, new = Path(rename.old), Path(rename.new)
    if not os.path.lexists(new) and old.is_file():
        return
    move_file(new, old)


def _rebuild(copy: Path, target: Path, record: FileRecord) -> None:
    """Rebuild ``target`` from the tag bytes in ``copy`` and its current audio stream."""
    tags = record.tags
    assert tags is not None  # noqa: S101 - only called for tag records
    region = audio_region(target)
    temporary = target.with_name(f".{target.name}.tunedex-{secrets.token_hex(4)}.tmp")
    try:
        with copy.open("rb") as kept, target.open("rb") as current, temporary.open("wb") as out:
            out.write(kept.read(tags.audio_start))
            copy_range(current, region.start, region.end, out.write)
            shutil.copyfileobj(kept, out)
            out.flush()
            os.fsync(out.fileno())
        if _sha256(temporary) != record.sha256:
            raise SnapshotError(f"{target}: the rebuilt file does not match the snapshot")
        shutil.copymode(target, temporary)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _is_sqlite(path: Path) -> bool:
    with path.open("rb") as file:
        return file.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER


def _sqlite_backup(source: Path, copy: Path) -> None:
    reader = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    try:
        writer = sqlite3.connect(copy)
        try:
            reader.backup(writer)
        finally:
            writer.close()
    finally:
        reader.close()


def _replace_file(copy: Path, target: Path, sha256: str) -> None:
    """Atomically replace ``target`` with ``copy`` via a temporary file in its directory."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tunedex-{secrets.token_hex(4)}.tmp")
    try:
        shutil.copyfile(copy, temporary)
        _fsync(temporary)
        if _sha256(temporary) != sha256:
            raise SnapshotError(f"{target}: copy changed while restoring")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_temporary(directory: Path) -> None:
    for entry in directory.iterdir():
        if entry.name.startswith(_TEMPORARY_PREFIX):
            shutil.rmtree(entry, ignore_errors=True)


def _sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _fsync(path: Path) -> None:
    with path.open("rb+") as file:
        os.fsync(file.fileno())


def _write_synced(path: Path, data: bytes) -> None:
    with path.open("wb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
