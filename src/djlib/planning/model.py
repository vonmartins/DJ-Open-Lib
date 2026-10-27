"""Plans: what a scan or an export would change, and how to carry it out."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from djlib.adapters.contract import Adapter, FileChange, Loss, WritePlan
from djlib.model.ids import NodeId, TrackId
from djlib.sources.scan_plan import ScanOperation

TrackChangeKind = Literal["added", "updated", "moved", "missing", "present"]
NodeChangeKind = Literal["added", "updated"]
NodeKind = Literal["folder", "playlist", "smartlist"]
ApplyStatus = Literal["applied", "declined", "nothing"]

LIBRARY_TARGET = "library"


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One field's value before and after, as model values (``Key``, ``date``…)."""

    field: str
    before: Any
    after: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackChange:
    change: TrackChangeKind
    track_id: TrackId | None
    path: str
    label: str
    fields: tuple[FieldChange, ...] = ()
    old_path: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeChange:
    """A playlist, smartlist or folder that is added or updated.

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
    """A field edited in djlib whose tag also changed in the file; djlib's value is kept."""

    track_id: TrackId
    path: str
    label: str
    field: str
    library_value: Any
    file_value: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class ScanAction:
    operations: tuple[ScanOperation, ...]
    base_revision: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportAction:
    adapter: Adapter
    write_plan: WritePlan
    fingerprints: Mapping[NodeId, str] = field(default_factory=dict[NodeId, str])
    """Fingerprints of the written nodes, recorded as sync state on success."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Plan:
    target: str
    """Snapshot target name: ``library`` or ``<adapter>-<12 hex digits>``."""
    title: str
    action: ScanAction | ExportAction
    tracks: tuple[TrackChange, ...] = ()
    nodes: tuple[NodeChange, ...] = ()
    refreshed: int = 0
    """File states refreshed without any field change (scans only)."""
    untouched_nodes: int = 0
    """Playlists in the target that the library does not have (exports only)."""
    losses: tuple[Loss, ...] = ()
    warnings: tuple[str, ...] = ()
    conflicts: tuple[FieldConflict, ...] = ()

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
    def empty(self) -> bool:
        if isinstance(self.action, ScanAction):
            return not self.action.operations
        return not self.action.write_plan.changes


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplyResult:
    status: ApplyStatus
    snapshot: str | None = None
    files_written: int = 0
    operations_applied: int = 0
    warnings: tuple[str, ...] = ()
