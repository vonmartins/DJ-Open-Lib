"""Changes to the library from scans, imports and relocations, applied atomically by the store.

Each operation carries the complete resulting values, so applying it needs no
recomputation.
"""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

from djlib.model.ids import TrackId
from djlib.model.playlist import Folder
from djlib.model.track import Track
from djlib.model.unmapped import JSONValue
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


# Imports from adapters. ``values`` are the source's encoded field values: the merge
# base for the next import from the same source. ``item_key`` is the source's own id of
# the item, kept to link the track to it.


@dataclass(frozen=True, slots=True)
class RegisterSource:
    """Create or refresh the source row; applied before the other import operations."""

    source: str
    imported_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class AddImportedTrack:
    track: Track
    source: str
    values: Mapping[str, JSONValue]
    item_key: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateImportedTrack:
    """Merged values changed the track: the stored track is replaced as a whole."""

    track: Track
    source: str
    values: Mapping[str, JSONValue]
    item_key: str | None = None


@dataclass(frozen=True, slots=True)
class RecordSourceValues:
    """Only the merge base changed."""

    track_id: TrackId
    source: str
    values: Mapping[str, JSONValue]
    item_key: str | None = None


@dataclass(frozen=True, slots=True)
class ReplaceSourceFolder:
    """Make the source's folder equal to ``folder``, keeping the ids of the nodes given.

    The folder is appended at the root when the source has none yet.
    """

    source: str
    folder: Folder


ImportOperation: TypeAlias = (
    RegisterSource
    | AddImportedTrack
    | UpdateImportedTrack
    | RecordSourceValues
    | ReplaceSourceFolder
)


@dataclass(frozen=True, slots=True)
class RelocateTrack:
    """The track's file was found at another path; only the path changes."""

    track_id: TrackId
    path_origin: str


@dataclass(frozen=True, slots=True)
class EditTrack:
    """The track's fields were edited in djlib (by fixes or rules); its path stays."""

    track: Track


LibraryOperation: TypeAlias = ScanOperation | ImportOperation | RelocateTrack | EditTrack
