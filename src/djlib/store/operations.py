"""Changes to the store produced by a folder scan, applied atomically by ``Store.apply_scan``.

Each operation carries the complete resulting values, so applying it needs no
recomputation.
"""

from dataclasses import dataclass
from typing import TypeAlias

from djlib.model.ids import TrackId
from djlib.model.track import Track
from djlib.store.file_state import FileState


@dataclass(frozen=True, slots=True)
class AddTrack:
    track: Track
    state: FileState


@dataclass(frozen=True, slots=True)
class UpdateTrack:
    """The file's tags changed: the stored track is replaced as a whole."""

    track: Track
    state: FileState


@dataclass(frozen=True, slots=True)
class MoveTrack:
    """The file moved: same track (id, cues, playlist entries), new path."""

    track: Track
    state: FileState
    old_path: str


@dataclass(frozen=True, slots=True)
class MarkMissing:
    track_id: TrackId


@dataclass(frozen=True, slots=True)
class MarkPresent:
    track_id: TrackId
    state: FileState


@dataclass(frozen=True, slots=True)
class RefreshState:
    """The file was touched but no field changed."""

    track_id: TrackId
    state: FileState


ScanOperation: TypeAlias = (
    AddTrack | UpdateTrack | MoveTrack | MarkMissing | MarkPresent | RefreshState
)
