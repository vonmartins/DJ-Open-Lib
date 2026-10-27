"""Choosing which playlists an export writes: by path, or those changed since the last export."""

import difflib
import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

from djlib.adapters.contract import Capabilities
from djlib.model.ids import NodeId, TrackId
from djlib.model.library import Library
from djlib.model.paths import normalize_path
from djlib.model.playlist import Folder, Playlist
from djlib.model.unmapped import JSONValue
from djlib.planning.errors import UnknownPlaylistError
from djlib.planning.render import json_value
from djlib.planning.tree import PlacedNode, by_path, kind_of, show_path, walk


def target_name(adapter: str, location: Path) -> str:
    """The snapshot and sync state name of an export target."""
    normalized = normalize_path(os.fspath(location.absolute()), entity="Target", field="location")
    return f"{adapter}-{hashlib.sha256(normalized.encode()).hexdigest()[:12]}"


def resolve_paths(library: Library, paths: Iterable[str]) -> frozenset[NodeId]:
    """Ids of the nodes at ``paths`` such as ``Techno/Peak`` (exact, case-sensitive names)."""
    nodes = by_path(library)
    ids: set[NodeId] = set()
    for text in paths:
        path = tuple(part for part in text.strip("/").split("/") if part)
        placed = nodes.get(path)
        if placed is None:
            known = [show_path(p) for p in nodes]
            raise UnknownPlaylistError(text, difflib.get_close_matches(text, known, n=3))
        ids.add(placed.node.id)
    return frozenset(ids)


def covered(library: Library, selection: frozenset[NodeId] | None) -> list[PlacedNode]:
    """The selected nodes and everything inside them; every node when ``selection`` is None."""
    return [
        p
        for p in walk(library)
        if selection is None or p.node.id in selection or not selection.isdisjoint(p.ancestors)
    ]


def fingerprints(
    library: Library, capabilities: Capabilities, nodes: Iterable[PlacedNode] | None = None
) -> dict[NodeId, str]:
    """A fingerprint per node of what an export with ``capabilities`` writes of it."""
    return {
        p.node.id: _fingerprint(p, library, capabilities)
        for p in (walk(library) if nodes is None else nodes)
    }


def modified(
    library: Library, capabilities: Capabilities, recorded: Mapping[NodeId, str]
) -> frozenset[NodeId]:
    """Nodes whose fingerprint differs from the one recorded at the last export, or has none."""
    current = fingerprints(library, capabilities)
    return frozenset(node_id for node_id, fp in current.items() if recorded.get(node_id) != fp)


def _fingerprint(placed: PlacedNode, library: Library, capabilities: Capabilities) -> str:
    node = placed.node
    document: dict[str, JSONValue] = {"path": list(placed.path), "kind": kind_of(node)}
    if isinstance(node, Folder):
        document["children"] = [c.name for c in node.children]
    elif isinstance(node, Playlist):
        document["entries"] = [
            _track_document(library, entry, capabilities) for entry in node.entries
        ]
    else:
        document["match"] = node.match.value
        document["rules"] = json_value(node.rules)
    text = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _track_document(
    library: Library, entry: TrackId, capabilities: Capabilities
) -> dict[str, JSONValue]:
    track = library.tracks[entry]
    document: dict[str, JSONValue] = {"path": track.path}
    for name in sorted(capabilities.track_fields):
        document[name] = json_value(getattr(track, name))
    if capabilities.cue_kinds:
        document["cues"] = json_value(
            tuple(c for c in track.cues if c.kind in capabilities.cue_kinds)
        )
    if capabilities.beatgrid:
        document["beatgrid"] = json_value(track.beatgrid)
    return document
