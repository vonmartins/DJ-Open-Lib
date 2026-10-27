"""Snapshot records and their JSON manifest (version 1)."""

import datetime
import json
from dataclasses import dataclass
from typing import Any, Literal

from djlib.snapshots.errors import SnapshotCorruptError

MANIFEST_VERSION = 1
CopyMethod = Literal["copy", "sqlite"]


@dataclass(frozen=True, slots=True, kw_only=True)
class FileRecord:
    """One file of a target: either present (with size and hash) or absent."""

    path: str
    present: bool
    size: int | None = None
    sha256: str | None = None
    method: CopyMethod | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Snapshot:
    id: str
    target: str
    created_at: datetime.datetime
    djlib_version: str
    reason: str | None
    files: tuple[FileRecord, ...]

    @property
    def sequence(self) -> int:
        return int(self.id.split("-", 1)[0])


def dump_manifest(snapshot: Snapshot) -> str:
    files: list[dict[str, Any]] = []
    for record in snapshot.files:
        if record.present:
            files.append(
                {"path": record.path, "present": True, "size": record.size,
                 "sha256": record.sha256, "method": record.method}
            )  # fmt: skip
        else:
            files.append({"path": record.path, "present": False})
    document = {
        "manifest_version": MANIFEST_VERSION,
        "id": snapshot.id,
        "target": snapshot.target,
        "created_at": snapshot.created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "djlib_version": snapshot.djlib_version,
        "reason": snapshot.reason,
        "files": files,
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def load_manifest(text: str) -> Snapshot:
    """Parse a manifest, raising ``SnapshotCorruptError`` if it is not a valid version 1."""
    try:
        document = json.loads(text)
        if document["manifest_version"] != MANIFEST_VERSION:
            raise SnapshotCorruptError(
                f"unsupported manifest version {document['manifest_version']!r}"
            )
        files = tuple(_load_record(entry) for entry in document["files"])
        created_at = datetime.datetime.strptime(document["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        return Snapshot(
            id=_text(document["id"]),
            target=_text(document["target"]),
            created_at=created_at.replace(tzinfo=datetime.UTC),
            djlib_version=_text(document["djlib_version"]),
            reason=None if document["reason"] is None else _text(document["reason"]),
            files=files,
        )
    except SnapshotCorruptError:
        raise
    except (ValueError, KeyError, TypeError) as error:
        raise SnapshotCorruptError(f"invalid manifest: {error}") from error


def _load_record(entry: dict[str, Any]) -> FileRecord:
    path = _text(entry["path"])
    if entry["present"] is False:
        return FileRecord(path=path, present=False)
    if entry["present"] is not True:
        raise ValueError("'present' must be a boolean")
    size, digest, method = entry["size"], entry["sha256"], entry["method"]
    if type(size) is not int or size < 0:
        raise ValueError("'size' must be a non-negative integer")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("'sha256' must be a hex digest")
    if method not in ("copy", "sqlite"):
        raise ValueError(f"unknown copy method {method!r}")
    return FileRecord(path=path, present=True, size=size, sha256=digest, method=method)


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected text, got {type(value).__name__}")
    return value
