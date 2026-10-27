"""Turning scan plans and export targets into lists of changes with before and after values."""

from collections import Counter
from collections.abc import Iterable, Sequence

from djlib.adapters.contract import Capabilities
from djlib.adapters.losses import TRACK_FIELDS, display_name
from djlib.model.ids import NodeId
from djlib.model.library import Library
from djlib.model.playlist import Folder, Playlist, Smartlist
from djlib.model.track import Track
from djlib.planning.model import FieldChange, NodeChange, TrackChange, TrackChangeKind
from djlib.planning.tree import PlacedNode, by_path, kind_of, walk
from djlib.sources.scan_plan import (
    AddTrack,
    MarkMissing,
    MarkPresent,
    MoveTrack,
    RefreshState,
    ScanPlan,
    UpdateTrack,
)
from djlib.store import Store

# Compared as a whole and reported as one field each.
COMPOSITE_FIELDS = ("tags", "cues", "beatgrid")


def diff_tracks(
    before: Track, after: Track, fields: Iterable[str] | None = None
) -> tuple[FieldChange, ...]:
    """Field changes from ``before`` to ``after`` (all fields except ids and paths)."""
    names = (*TRACK_FIELDS, *COMPOSITE_FIELDS) if fields is None else tuple(fields)
    return tuple(
        FieldChange(name, getattr(before, name), getattr(after, name))
        for name in names
        if getattr(before, name) != getattr(after, name)
    )


def diff_scan(store: Store, plan: ScanPlan) -> tuple[tuple[TrackChange, ...], int]:
    """Track changes of a scan plan against the store, and the number of refreshes."""
    changes: list[TrackChange] = []
    refreshed = 0
    for operation in plan.operations:
        match operation:
            case AddTrack(track, _):
                changes.append(_change("added", track))
            case UpdateTrack(track, _):
                fields = diff_tracks(store.get_track(track.id), track)
                changes.append(_change("updated", track, fields))
            case MoveTrack(track, _, old_path):
                fields = diff_tracks(store.get_track(track.id), track)
                changes.append(_change("moved", track, fields, old_path=old_path))
            case MarkMissing(track_id):
                changes.append(_change("missing", store.get_track(track_id)))
            case MarkPresent(track_id, _):
                changes.append(_change("present", store.get_track(track_id)))
            case RefreshState():
                refreshed += 1
    return tuple(changes), refreshed


def _change(
    kind: TrackChangeKind,
    track: Track,
    fields: tuple[FieldChange, ...] = (),
    *,
    old_path: str | None = None,
) -> TrackChange:
    return TrackChange(
        change=kind,
        track_id=track.id,
        path=track.path,
        label=display_name(track),
        fields=fields,
        old_path=old_path,
    )


def diff_export(
    current: Library,
    desired: Library,
    selection: frozenset[NodeId] | None,
    capabilities: Capabilities,
) -> tuple[tuple[NodeChange, ...], tuple[TrackChange, ...], int]:
    """Node changes, track changes and untouched node count for writing ``desired``.

    ``current`` is what the target holds now, read back into library paths. Nodes are
    matched by path, tracks by normalized path.
    """
    existing = by_path(current)
    wanted = [p for p in walk(desired) if _selected(p, selection)]
    nodes = [
        change
        for placed in wanted
        if (change := _node_change(placed, existing.get(placed.path), current, desired))
    ]
    all_desired = {p.path for p in walk(desired)}
    untouched = sum(
        1
        for path, placed in existing.items()
        if path not in all_desired and not isinstance(placed.node, Folder)
    )
    tracks: list[TrackChange] = []
    if capabilities.collection:
        fields = [f for f in TRACK_FIELDS if f in capabilities.track_fields]
        current_tracks = {t.path: t for t in current.tracks.values()}
        for track in sorted(desired.tracks.values(), key=lambda t: t.path):
            old = current_tracks.get(track.path)
            if old is None:
                tracks.append(_change("added", track))
            elif changed := diff_tracks(old, track, fields):
                tracks.append(_change("updated", track, changed))
    return tuple(nodes), tuple(tracks), untouched


def _selected(placed: PlacedNode, selection: frozenset[NodeId] | None) -> bool:
    if selection is None:
        return True
    return placed.node.id in selection or not selection.isdisjoint(placed.ancestors)


def _node_change(
    placed: PlacedNode, old: PlacedNode | None, current: Library, desired: Library
) -> NodeChange | None:
    node = placed.node
    kind = kind_of(node)
    entries = _entries(node, desired)
    if old is None:
        return NodeChange(change="added", path=placed.path, kind=kind, entries_added=entries)
    if kind_of(old.node) != kind:
        return NodeChange(
            change="updated",
            path=placed.path,
            kind=kind,
            entries_added=entries,
            entries_removed=_entries(old.node, current),
        )
    if isinstance(node, Smartlist) and isinstance(old.node, Smartlist):
        same = (node.match, node.rules) == (old.node.match, old.node.rules)
        return None if same else NodeChange(change="updated", path=placed.path, kind=kind)
    before = (
        [c.name for c in old.node.children]
        if isinstance(old.node, Folder)
        else list(_entries(old.node, current))
    )
    after = [c.name for c in node.children] if isinstance(node, Folder) else list(entries)
    if before == after:
        return None
    added, removed = _multiset_difference(after, before), _multiset_difference(before, after)
    if isinstance(node, Folder):
        # Folder children are compared on their own; only the order matters here.
        return None if added or removed else _reordered(placed)
    common_before = [e for e in before if e not in set(removed)]
    common_after = [e for e in after if e not in set(added)]  # order of the shared entries
    return NodeChange(
        change="updated",
        path=placed.path,
        kind=kind,
        entries_added=added,
        entries_removed=removed,
        reordered=common_before != common_after,
    )


def _reordered(placed: PlacedNode) -> NodeChange:
    return NodeChange(change="updated", path=placed.path, kind="folder", reordered=True)


def _entries(node: object, library: Library) -> tuple[str, ...]:
    if not isinstance(node, Playlist):
        return ()
    return tuple(library.tracks[e].path for e in node.entries)


def _multiset_difference(left: Sequence[str], right: Sequence[str]) -> tuple[str, ...]:
    remaining = Counter(right)
    result: list[str] = []
    for item in left:
        if remaining[item]:
            remaining[item] -= 1
        else:
            result.append(item)
    return tuple(result)
