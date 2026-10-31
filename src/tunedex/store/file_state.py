"""What a folder scan last saw of a track's file."""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field

from tunedex.model.ids import TrackId
from tunedex.model.unmapped import JSONValue


@dataclass(frozen=True, slots=True, kw_only=True)
class FileState:
    track_id: TrackId
    size: int
    mtime_ns: int
    quick_hash: str
    scanned_at: datetime.datetime
    missing: bool = False
    scanned_values: Mapping[str, JSONValue] = field(default_factory=dict[str, JSONValue])
    """Field values read from the file at the last scan, used as the merge base."""
