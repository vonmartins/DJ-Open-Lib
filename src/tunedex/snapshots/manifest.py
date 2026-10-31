"""Snapshot records and their JSON manifest (version 1)."""

import datetime
import json
from dataclasses import dataclass
from typing import Any, Literal

from tunedex.snapshots.errors import SnapshotCorruptError

MANIFEST_VERSION = 1
CopyMethod = Literal["copy", "sqlite", "tags"]


@dataclass(frozen=True, slots=True, kw_only=True)
class TagBytes:
    """What a tag snapshot holds of a file: the bytes before and after its audio stream.

    The copy is those bytes one after the other; the audio stream is not copied.
    """

    audio_start: int
    audio_end: int
    audio_sha256: str
    copy_sha256: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FileRecord:
    """One file of a target: either present (with size and hash) or absent.

    Size and hash are the whole file's. Tag snapshots (method ``tags``) copy only the
    bytes outside the audio stream, described by ``tags``.
    """

    path: str
    present: bool
    size: int | None = None
    sha256: str | None = None
    method: CopyMethod | None = None
    tags: TagBytes | None = None

    @property
    def copy_size(self) -> int | None:
        """Size of the copy in the snapshot."""
        if self.tags is None or self.size is None:
            return self.size
        return self.tags.audio_start + self.size - self.tags.audio_end

    @property
    def copy_sha256(self) -> str | None:
        return self.sha256 if self.tags is None else self.tags.copy_sha256


@dataclass(frozen=True, slots=True)
class Rename:
    """A file named ``old`` at snapshot time and ``new`` after; restoring names it ``old``."""

    old: str
    new: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Snapshot:
    id: str
    target: str
    created_at: datetime.datetime
    tunedex_version: str
    reason: str | None
    files: tuple[FileRecord, ...]
    renames: tuple[Rename, ...] = ()

    @property
    def sequence(self) -> int:
        return int(self.id.split("-", 1)[0])


def dump_manifest(snapshot: Snapshot) -> str:
    files: list[dict[str, Any]] = []
    for record in snapshot.files:
        if record.present:
            entry: dict[str, Any] = {"path": record.path, "present": True, "size": record.size,
                                     "sha256": record.sha256, "method": record.method}  # fmt: skip
            if record.tags is not None:
                entry.update(
                    audio_start=record.tags.audio_start,
                    audio_end=record.tags.audio_end,
                    audio_sha256=record.tags.audio_sha256,
                    copy_sha256=record.tags.copy_sha256,
                )
            files.append(entry)
        else:
            files.append({"path": record.path, "present": False})
    document = {
        "manifest_version": MANIFEST_VERSION,
        "id": snapshot.id,
        "target": snapshot.target,
        "created_at": snapshot.created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "tunedex_version": snapshot.tunedex_version,
        "reason": snapshot.reason,
        "files": files,
    }
    if snapshot.renames:
        document["renames"] = [{"old": r.old, "new": r.new} for r in snapshot.renames]
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
            tunedex_version=_text(document["tunedex_version"]),
            reason=None if document["reason"] is None else _text(document["reason"]),
            files=files,
            renames=tuple(
                Rename(_text(entry["old"]), _text(entry["new"]))
                for entry in document.get("renames", [])
            ),
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
    if method not in ("copy", "sqlite", "tags"):
        raise ValueError(f"unknown copy method {method!r}")
    tags = None
    if method == "tags":
        start, end = entry["audio_start"], entry["audio_end"]
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= size:
            raise ValueError("'audio_start' and 'audio_end' must be offsets in the file")
        tags = TagBytes(
            audio_start=start,
            audio_end=end,
            audio_sha256=_digest(entry["audio_sha256"]),
            copy_sha256=_digest(entry["copy_sha256"]),
        )
    return FileRecord(path=path, present=True, size=size, sha256=digest, method=method, tags=tags)


def _digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("expected a hex digest")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected text, got {type(value).__name__}")
    return value
