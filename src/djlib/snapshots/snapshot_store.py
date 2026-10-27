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

from djlib.snapshots.errors import RestoreError, SnapshotCorruptError, SnapshotError
from djlib.snapshots.manifest import (
    CopyMethod,
    FileRecord,
    Snapshot,
    dump_manifest,
    load_manifest,
)

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

    def create(self, target: str, files: Iterable[Path], *, reason: str | None = None) -> Snapshot:
        """Copy ``files`` (absolute paths; missing ones are recorded as absent)."""
        return self._create(target, _check_files(files), reason=reason, protect=())

    def _create(
        self, target: str, paths: list[Path], *, reason: str | None, protect: Collection[str]
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
                _copy_in(path, temporary / "files" / str(index)) for index, path in enumerate(paths)
            )
            snapshot = Snapshot(
                id=snapshot_id,
                target=target,
                created_at=created_at,
                djlib_version=self._version or version("djlib"),
                reason=reason,
                files=records,
            )
            _write_synced(temporary / MANIFEST, dump_manifest(snapshot).encode("utf-8"))
            temporary.rename(directory / snapshot_id)
        except (OSError, sqlite3.Error) as error:
            shutil.rmtree(temporary, ignore_errors=True)
            raise SnapshotError(f"cannot snapshot target {target!r}: {error}") from error

        self.prune(target, protect=protect)
        return snapshot

    # Listing

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
            if copy.stat().st_size != record.size or _sha256(copy) != record.sha256:
                raise SnapshotCorruptError(f"{record.path}: copy does not match the manifest")

    def restore(self, snapshot: Snapshot) -> RestoreResult:
        """Put every target file back to the state recorded in ``snapshot``.

        The current state is snapshotted first. Databases must not be open in any
        store while they are restored.
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

        paths = [Path(record.path) for record in snapshot.files]
        pre_restore = self._create(
            snapshot.target, paths, reason="pre-restore", protect={snapshot.id}
        )
        try:
            self._apply(snapshot)
        except (OSError, SnapshotError) as error:
            try:
                self._apply(pre_restore)
            except (OSError, SnapshotError) as rollback_error:
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

    def _apply(self, snapshot: Snapshot) -> None:
        files = self._snapshot_dir(snapshot) / "files"
        for index, record in enumerate(snapshot.files):
            target = Path(record.path)
            if record.present:
                _replace_file(files / str(index), target, record.sha256 or "")
            else:
                target.unlink(missing_ok=True)
        for record in snapshot.files:
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


def _copy_in(source: Path, copy: Path) -> FileRecord:
    if not source.exists():
        return FileRecord(path=os.fspath(source), present=False)
    method: CopyMethod = "copy"
    if _is_sqlite(source):
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
    temporary = target.with_name(f".{target.name}.djlib-{secrets.token_hex(4)}.tmp")
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
