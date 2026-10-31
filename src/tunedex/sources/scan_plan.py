"""The result of scanning a folder: operations to apply, conflicts and warnings."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tunedex.model.ids import TrackId
from tunedex.store.operations import (
    AddTrack,
    MarkMissing,
    MarkPresent,
    MoveTrack,
    RefreshState,
    ScanOperation,
    UpdateTrack,
)

__all__ = [
    "AddTrack",
    "Conflict",
    "MarkMissing",
    "MarkPresent",
    "MoveTrack",
    "RefreshState",
    "ScanOperation",
    "ScanPlan",
    "UpdateTrack",
]


@dataclass(frozen=True, slots=True)
class Conflict:
    """A field edited in tunedex whose tag also changed in the file; tunedex's value was kept."""

    track_id: TrackId
    field: str
    library_value: Any
    file_value: Any


@dataclass(frozen=True, slots=True)
class ScanPlan:
    root: Path
    operations: tuple[ScanOperation, ...]
    conflicts: tuple[Conflict, ...] = ()
    warnings: tuple[str, ...] = ()
