"""The interface every format adapter implements, and the values it exchanges.

Adapters read external formats into the canonical model and plan writes as complete
file contents. They never write to disk: the plan/apply engine checks the base hashes,
snapshots the target and writes atomically.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from djlib.adapters.pathmap import PathMapping
from djlib.model.cue import CueKind
from djlib.model.ids import NodeId
from djlib.model.library import Library

MAX_LOSS_EXAMPLES = 5


@dataclass(frozen=True, slots=True, kw_only=True)
class Capabilities:
    """What a format can hold. ``track_fields`` uses ``Track`` attribute names."""

    track_fields: frozenset[str]
    cue_kinds: frozenset[CueKind] = frozenset()
    beatgrid: bool = False
    tags: bool = False
    folders: bool = False
    smartlists: bool = False
    collection: bool = False
    """Whether tracks that are in no playlist can be stored."""
    updated_fields: frozenset[str] | None = None
    """Fields written to tracks the target already has; ``None`` means ``track_fields``.

    The other fields are written only for tracks a write adds.
    """

    @property
    def fields_updated(self) -> frozenset[str]:
        return self.track_fields if self.updated_fields is None else self.updated_fields


@dataclass(frozen=True, slots=True)
class Detection:
    matches: bool
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ReadOptions:
    path_mapping: PathMapping = field(default_factory=PathMapping)


@dataclass(frozen=True, slots=True, kw_only=True)
class ReadResult:
    library: Library
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class WriteOptions:
    path_mapping: PathMapping = field(default_factory=PathMapping)
    selection: frozenset[NodeId] | None = None
    """Playlist and folder ids to write; ``None`` writes everything."""
    source_root: NodeId | None = None
    """The folder that imports from this location fill, when the location is a source."""


@dataclass(frozen=True, slots=True, kw_only=True)
class FileChange:
    """A file to create or update with ``content``.

    ``base_sha256`` is the hash of the file's current content, or ``None`` when it does
    not exist yet.
    """

    path: Path
    content: bytes
    base_sha256: str | None
    description: str

    def __post_init__(self) -> None:
        if not self.path.is_absolute():
            raise ValueError(f"file changes need absolute paths, got {self.path}")

    @property
    def action(self) -> Literal["create", "update"]:
        return "create" if self.base_sha256 is None else "update"


@dataclass(frozen=True, slots=True, kw_only=True)
class Loss:
    """Data of one kind the target cannot represent."""

    kind: str
    description: str
    count: int
    examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("a loss affects at least one item")
        if len(self.examples) > MAX_LOSS_EXAMPLES:
            raise ValueError(f"a loss lists at most {MAX_LOSS_EXAMPLES} examples")


@dataclass(frozen=True, slots=True, kw_only=True)
class WritePlan:
    adapter: str
    location: Path
    changes: tuple[FileChange, ...] = ()
    losses: tuple[Loss, ...] = ()
    warnings: tuple[str, ...] = ()
    view: Library | None = None
    """The written tracks and nodes as the target holds them after the write, read back.

    Nodes keep the ids of the library nodes they come from. Plans compare the target
    with the view instead of the library when it is given.
    """
    check: Callable[[], None] | None = None
    """Run by the engine right before writing; raises ``AdapterError`` to stop."""


class Adapter(Protocol):
    """A format adapter. Format-specific settings are constructor arguments."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> Capabilities: ...

    def detect(self, location: Path) -> Detection:
        """Whether ``location`` is in this format. Never modifies anything."""
        ...

    def read(self, location: Path, options: ReadOptions | None = None) -> ReadResult:
        """Read ``location`` into a library. Never creates, modifies or deletes files."""
        ...

    def plan_write(
        self, library: Library, location: Path, options: WriteOptions | None = None
    ) -> WritePlan:
        """Plan writing ``library`` to ``location``. Never writes anything."""
        ...
