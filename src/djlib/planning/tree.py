"""Playlist nodes addressed by their path of names from the root."""

from collections.abc import Iterator
from dataclasses import dataclass

from djlib.model.ids import NodeId
from djlib.model.library import Library
from djlib.model.playlist import Folder, Node, Playlist
from djlib.planning.model import NodeKind

NodePath = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlacedNode:
    path: NodePath
    node: Node
    ancestors: tuple[NodeId, ...]


def walk(library: Library) -> Iterator[PlacedNode]:
    """Every node, depth first in tree order, with its path and ancestor ids."""
    stack: list[tuple[Node, NodePath, tuple[NodeId, ...]]] = [
        (node, (node.name,), ()) for node in reversed(library.playlists)
    ]
    while stack:
        node, path, ancestors = stack.pop()
        yield PlacedNode(path, node, ancestors)
        if isinstance(node, Folder):
            inner = (*ancestors, node.id)
            stack.extend((c, (*path, c.name), inner) for c in reversed(node.children))


def by_path(library: Library) -> dict[NodePath, PlacedNode]:
    """Nodes keyed by path; when siblings share a name, the first one wins."""
    placed: dict[NodePath, PlacedNode] = {}
    for item in walk(library):
        placed.setdefault(item.path, item)
    return placed


def kind_of(node: Node) -> NodeKind:
    if isinstance(node, Folder):
        return "folder"
    return "playlist" if isinstance(node, Playlist) else "smartlist"


def show_path(path: NodePath) -> str:
    return "/".join(path)
