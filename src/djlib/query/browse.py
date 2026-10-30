"""Read-only views of the library: track selections, one track, the status, the playlists."""

import os
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from djlib.model.errors import ValidationError
from djlib.model.ids import TrackId
from djlib.model.library import Library
from djlib.model.playlist import Folder, Playlist, Smartlist
from djlib.model.track import Track
from djlib.planning.deduplicating import find_duplicates
from djlib.planning.model import NodeKind
from djlib.planning.selection import resolve_paths
from djlib.planning.tree import kind_of, show_path, walk
from djlib.rules.conditions import Condition, from_rule, holds
from djlib.snapshots import Snapshot, SnapshotStore
from djlib.store import NotFoundError, Store
from djlib.store.source_state import SourceInfo


def present(track: Track) -> bool:
    """Whether the track's file exists on this computer."""
    return Path(track.path_origin).exists()


def select(
    store: Store,
    *,
    where: Sequence[Condition] = (),
    under: str | os.PathLike[str] | None = None,
    playlists: Sequence[str] = (),
    missing: bool = False,
) -> list[Track]:
    """The tracks every given filter keeps, by artist, title and path, ignoring case.

    ``playlists`` are paths such as ``Sets/Friday``; a folder stands for every playlist
    and smartlist under it.
    """
    tracks = store.list_tracks() if under is None else store.list_tracks_under(os.fspath(under))
    if playlists:
        library = store.load_library()
        wanted = in_playlists(library, playlists)
        tracks = [t for t in tracks if t.id in wanted]
    tracks = [t for t in tracks if all(c.holds(t) for c in where)]
    if missing:
        tracks = [t for t in tracks if not present(t)]
    return sorted(tracks, key=_order)


def _order(track: Track) -> tuple[str, str, str]:
    return ((track.artist or "").casefold(), (track.title or "").casefold(), track.path)


def in_playlists(library: Library, paths: Iterable[str]) -> set[TrackId]:
    """The tracks of the playlists and smartlists at ``paths`` or under those folders."""
    chosen = resolve_paths(library, paths)
    found: set[TrackId] = set()
    for placed in walk(library):
        if placed.node.id not in chosen and chosen.isdisjoint(placed.ancestors):
            continue
        found.update(_entries(library, placed.node))
    return found


def _entries(library: Library, node: Playlist | Smartlist | Folder) -> Iterable[TrackId]:
    if isinstance(node, Playlist):
        return node.entries
    if isinstance(node, Smartlist):
        conditions = [from_rule(rule) for rule in node.rules]
        return [t.id for t in library.tracks.values() if holds(conditions, node.match, t)]
    return ()


# One track


@dataclass(frozen=True, slots=True)
class TrackView:
    track: Track
    present: bool
    playlists: tuple[str, ...]
    """Paths of the playlists and smartlists that hold the track, in tree order."""
    sources: tuple[str, ...]


def find_track(store: Store, ref: str) -> Track:
    """The track whose id or path is ``ref``; ``NotFoundError`` naming it otherwise."""
    try:
        return store.get_track(TrackId(uuid.UUID(ref)))
    except (ValueError, NotFoundError):
        pass
    try:
        track = store.find_track_by_path(ref)
    except ValidationError:
        track = None
    if track is None:
        raise NotFoundError(f"no track has the id or path {ref}")
    return track


def track_view(store: Store, ref: str) -> TrackView:
    track = find_track(store, ref)
    library = store.load_library()
    playlists = tuple(
        show_path(placed.path)
        for placed in walk(library)
        if not isinstance(placed.node, Folder) and track.id in set(_entries(library, placed.node))
    )
    return TrackView(track, present(track), playlists, tuple(store.sources_of(track.id)))


# Status


@dataclass(frozen=True, slots=True)
class Status:
    tracks: int
    missing: int
    playlists: int
    smartlists: int
    folders: int
    sources: tuple[SourceInfo, ...]
    snapshots: tuple[Snapshot, ...]
    """The newest snapshot of each target, by target name."""
    duplicate_groups: int


def status(store: Store, snapshots: SnapshotStore) -> Status:
    library = store.load_library()
    kinds = [kind_of(placed.node) for placed in walk(library)]
    newest = (snapshots.list(target) for target in snapshots.targets())
    return Status(
        tracks=len(library.tracks),
        missing=sum(not present(t) for t in library.tracks.values()),
        playlists=kinds.count("playlist"),
        smartlists=kinds.count("smartlist"),
        folders=kinds.count("folder"),
        sources=tuple(store.sources()),
        snapshots=tuple(found[0] for found in newest if found),
        duplicate_groups=len(find_duplicates(store)),
    )


# Playlists


@dataclass(frozen=True, slots=True)
class TreeNode:
    name: str
    kind: NodeKind
    depth: int
    tracks: int | None
    """Tracks in a playlist or selected by a smartlist; ``None`` for folders."""
    path: str


def playlist_tree(store: Store) -> list[TreeNode]:
    """Every folder, playlist and smartlist, depth first in tree order."""
    library = store.load_library()
    return [
        TreeNode(
            name=placed.node.name,
            kind=kind_of(placed.node),
            depth=len(placed.ancestors),
            tracks=None
            if isinstance(placed.node, Folder)
            else len(set(_entries(library, placed.node))),
            path=show_path(placed.path),
        )
        for placed in walk(library)
    ]
