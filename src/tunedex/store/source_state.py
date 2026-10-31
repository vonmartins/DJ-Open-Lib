"""What the store remembers about an import source."""

import datetime
from dataclasses import dataclass

from tunedex.model.ids import NodeId


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceInfo:
    name: str
    root_node_id: NodeId | None
    """The folder holding the source's playlists; ``None`` once it was deleted."""
    imported_at: datetime.datetime
