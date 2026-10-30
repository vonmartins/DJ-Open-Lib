"""The playlist tree: folders, playlists and smartlists."""

import enum
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypeAlias

from tunedex.model._validate import check_text, set_field
from tunedex.model.errors import ValidationError
from tunedex.model.ids import NodeId, TrackId, new_node_id
from tunedex.model.unmapped import JSONValue, copy_json, copy_unmapped


class MatchMode(enum.Enum):
    ALL = "all"
    ANY = "any"


@dataclass(frozen=True, slots=True, kw_only=True)
class Rule:
    """One smartlist condition, stored as data. Evaluation belongs to the rules engine."""

    field: str
    operator: str
    values: tuple[JSONValue, ...] = ()

    def __post_init__(self) -> None:
        for name in ("field", "operator"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValidationError("Rule", name, "must be non-empty text")
        values = [
            copy_json(v, entity="Rule", field="values", where=f"values[{i}]")
            for i, v in enumerate(tuple(self.values))
        ]
        set_field(self, "values", tuple(values))


@dataclass(frozen=True, slots=True, kw_only=True)
class Playlist:
    """An ordered list of tracks; the same track may appear more than once."""

    name: str
    entries: tuple[TrackId, ...] = ()
    id: NodeId = field(default_factory=new_node_id)
    unmapped: Mapping[str, JSONValue] = field(default_factory=dict[str, JSONValue])

    def __post_init__(self) -> None:
        _check_node(self, "Playlist")
        entries = tuple(self.entries)
        if any(not isinstance(e, uuid.UUID) for e in entries):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Playlist", "entries", "must contain track identifiers")
        set_field(self, "entries", entries)


@dataclass(frozen=True, slots=True, kw_only=True)
class Smartlist:
    """A list defined by rules; it holds no tracks of its own."""

    name: str
    match: MatchMode = MatchMode.ALL
    rules: tuple[Rule, ...] = ()
    id: NodeId = field(default_factory=new_node_id)
    unmapped: Mapping[str, JSONValue] = field(default_factory=dict[str, JSONValue])

    def __post_init__(self) -> None:
        _check_node(self, "Smartlist")
        try:
            set_field(self, "match", MatchMode(self.match))
        except ValueError:
            raise ValidationError("Smartlist", "match", "must be 'all' or 'any'") from None
        rules = tuple(self.rules)
        if any(not isinstance(r, Rule) for r in rules):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Smartlist", "rules", "must contain Rule values")
        set_field(self, "rules", rules)


@dataclass(frozen=True, slots=True, kw_only=True)
class Folder:
    """A container of other nodes. Folders never hold tracks directly."""

    name: str
    children: tuple["Node", ...] = ()
    id: NodeId = field(default_factory=new_node_id)
    unmapped: Mapping[str, JSONValue] = field(default_factory=dict[str, JSONValue])

    def __post_init__(self) -> None:
        _check_node(self, "Folder")
        children = tuple(self.children)
        if any(not isinstance(c, Folder | Playlist | Smartlist) for c in children):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError(
                "Folder", "children", "must contain folders, playlists or smartlists, not tracks"
            )
        set_field(self, "children", children)


Node: TypeAlias = Folder | Playlist | Smartlist


def _check_node(node: Node, entity: str) -> None:
    check_text(entity, "name", node.name)
    if node.name is None:  # pyright: ignore[reportUnnecessaryComparison]
        raise ValidationError(entity, "name", "is required")
    if not isinstance(node.id, uuid.UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValidationError(entity, "id", "must be a node identifier")
    set_field(node, "unmapped", copy_unmapped(node.unmapped, entity=entity))
