"""Plans: what a scan or an export would change, and how to carry it out."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from tunedex.adapters.contract import Adapter, FileChange, Loss, WritePlan
from tunedex.model.ids import NodeId, TrackId
from tunedex.model.unmapped import JSONValue
from tunedex.store.operations import LibraryOperation

TrackChangeKind = Literal["added", "updated", "moved", "missing", "present", "merged"]
NodeChangeKind = Literal["added", "updated", "removed"]
NodeKind = Literal["folder", "playlist", "smartlist"]
ApplyStatus = Literal["applied", "declined", "nothing"]

LIBRARY_TARGET = "library"
TAGS_TARGET = "tags"
RENAMES_TARGET = "renames"


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One field's value before and after, as model values (``Key``, ``date``…)."""

    field: str
    before: Any
    after: Any
    by: str | None = None
    """What made the change, such as a fix name or rule id, when it is known."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackChange:
    change: TrackChangeKind
    track_id: TrackId | None
    path: str
    name: str
    """How the track is shown: ``artist - title``, or the file name."""
    fields: tuple[FieldChange, ...] = ()
    """Changed fields; for an added track, every field it has, from ``None``."""
    old_path: str | None = None
    merged_into: str | None = None
    """For a merged track, the path of the track it was merged into."""


@dataclass(frozen=True, slots=True)
class TrashFile:
    """An audio file to move to the system trash, as it was when planning."""

    path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeChange:
    """A playlist, smartlist or folder that is added, updated or removed.

    Only imports remove nodes, and only inside the source's folder.

    Entries are normalized track paths. ``renamed_from`` is set only by formats whose
    nodes have stable ids.
    """

    change: NodeChangeKind
    path: tuple[str, ...]
    kind: NodeKind
    entries_added: tuple[str, ...] = ()
    entries_removed: tuple[str, ...] = ()
    reordered: bool = False
    renamed_from: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FieldConflict:
    """A field edited in tunedex whose tag also changed in the file; tunedex's value is kept."""

    track_id: TrackId
    path: str
    name: str
    field: str
    library_value: Any
    file_value: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class LibraryAction:
    operations: tuple[LibraryOperation, ...]
    base_revision: int
    trash: tuple[TrashFile, ...] = ()
    """Audio files moved to the system trash once the library is written."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportAction:
    adapter: Adapter
    write_plan: WritePlan
    fingerprints: Mapping[NodeId, str] = field(default_factory=dict[NodeId, str])
    """Fingerprints of the written nodes, recorded as sync state on success."""
    target_paths: Mapping[NodeId, tuple[str, ...]] = field(
        default_factory=dict[NodeId, tuple[str, ...]]
    )
    """Where the target holds each written node, when its tree differs from the library's."""
    source_values: Mapping[TrackId, Mapping[str, JSONValue]] = field(
        default_factory=dict[TrackId, Mapping[str, JSONValue]]
    )
    """Merge bases recorded on success, for targets that hold a collection."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TagFile:
    """An audio file whose tags a plan writes, as it was when planning."""

    track_id: TrackId
    path: str
    """The file's path on disk."""
    size: int
    mtime_ns: int
    fields: Mapping[str, str | None]
    """The text each changed field is written as; ``None`` removes the field."""
    tag_bytes: int
    """How many bytes of the file are outside its audio stream: what the snapshot copies."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TagWriteAction:
    files: tuple[TagFile, ...]
    base_revision: int


@dataclass(frozen=True, slots=True)
class FileRename:
    """A track's file renamed in its folder; ``old`` and ``new`` are paths on disk."""

    track_id: TrackId
    old: str
    new: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RenameAction:
    renames: tuple[FileRename, ...]
    base_revision: int


Action = LibraryAction | ExportAction | TagWriteAction | RenameAction


@dataclass(frozen=True, slots=True, kw_only=True)
class Plan:
    """Every change a command would make, computed without writing anything."""

    target: str
    """Snapshot target name: ``library`` or ``<adapter>-<12 hex digits>``."""
    title: str
    action: Action
    tracks: tuple[TrackChange, ...] = ()
    nodes: tuple[NodeChange, ...] = ()
    refreshed: int = 0
    """File states refreshed without any field change (scans only)."""
    rebased: int = 0
    """Tracks whose merge base was updated without any field change (imports only)."""
    untouched_nodes: int = 0
    """Playlists in the target that the library does not have (exports only)."""
    losses: tuple[Loss, ...] = ()
    warnings: tuple[str, ...] = ()
    conflicts: tuple[FieldConflict, ...] = ()
    tags: tuple[TrackChange, ...] = ()
    """Files whose tags are written, with their fields: the file's value, then the library's."""

    @property
    def files(self) -> tuple[FileChange, ...]:
        if isinstance(self.action, ExportAction):
            return self.action.write_plan.changes
        return ()

    @property
    def location(self) -> Path | None:
        if isinstance(self.action, ExportAction):
            return self.action.write_plan.location
        return None

    @property
    def trash(self) -> tuple[TrashFile, ...]:
        if isinstance(self.action, LibraryAction):
            return self.action.trash
        return ()

    @property
    def snapshot_bytes(self) -> int:
        """For tag writes, about how much the tag snapshot takes."""
        if isinstance(self.action, TagWriteAction):
            return sum(f.tag_bytes for f in self.action.files)
        return 0

    @property
    def empty(self) -> bool:
        match self.action:
            case LibraryAction():
                return not self.action.operations and not self.action.trash
            case ExportAction():
                return not self.action.write_plan.changes
            case TagWriteAction():
                return not self.action.files
            case RenameAction():
                return not self.action.renames


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplyResult:
    """What applying a plan did: applied, declined, or nothing to do."""

    status: ApplyStatus
    snapshot: str | None = None
    files_written: int = 0
    operations_applied: int = 0
    files_trashed: int = 0
    files_renamed: int = 0
    warnings: tuple[str, ...] = ()
