"""Importing a library read by an adapter into djlib's library.

Tracks are matched by normalized path and merged three ways, with what the last import
from the same source read as the base. The source's playlists live in one folder that
the source owns: imports replace its contents and leave every other node alone.
"""

import dataclasses
import datetime
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from djlib.adapters.contract import Adapter, Capabilities, ReadOptions
from djlib.adapters.losses import TRACK_FIELDS, display_name
from djlib.adapters.pathmap import PathMapping
from djlib.model.encoding import to_json
from djlib.model.ids import NodeId, TrackId, new_node_id
from djlib.model.library import Library
from djlib.model.playlist import Folder, Node, Playlist
from djlib.model.track import Track
from djlib.model.unmapped import JSONValue
from djlib.planning.diff import diff_export, diff_tracks
from djlib.planning.model import (
    FieldChange,
    FieldConflict,
    NodeChange,
    TrackChange,
    TrackChangeKind,
)
from djlib.planning.selection import target_name
from djlib.planning.tree import NodePath, by_path, kind_of
from djlib.sources.merge import FieldDisagreement, merge_fields
from djlib.store import Store
from djlib.store.operations import (
    AddImportedTrack,
    ImportOperation,
    RecordSourceValues,
    RegisterSource,
    ReplaceSourceFolder,
    UpdateImportedTrack,
)

_NO_TRACK_DIFF = Capabilities(track_fields=frozenset(), folders=True)


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportPlan:
    source: str
    operations: tuple[ImportOperation, ...]
    tracks: tuple[TrackChange, ...]
    nodes: tuple[NodeChange, ...]
    conflicts: tuple[FieldConflict, ...]
    warnings: tuple[str, ...]
    rebased: int
    """Tracks whose merge base changed without any field change."""


def merged_fields(capabilities: Capabilities, *, updated: bool = False) -> tuple[str, ...]:
    """The fields an import from an adapter with ``capabilities`` merges.

    With ``updated``, only the fields an export writes to tracks the target has.
    """
    allowed = capabilities.fields_updated if updated else capabilities.track_fields
    fields = [name for name in TRACK_FIELDS if name in allowed]
    if capabilities.cue_kinds:
        fields.append("cues")
    if capabilities.beatgrid:
        fields.append("beatgrid")
    return tuple(fields)


def plan_import(
    store: Store,
    adapter: Adapter,
    location: str | os.PathLike[str],
    *,
    path_mapping: PathMapping | None = None,
    now: datetime.datetime,
) -> ImportPlan:
    """Plan importing what ``adapter`` reads at ``location``. Changes nothing."""
    location = Path(location).absolute()
    source = target_name(adapter.name, location)
    read = adapter.read(location, ReadOptions(path_mapping=path_mapping or PathMapping()))
    fields = merged_fields(adapter.capabilities)
    library_tracks = dict(store.load_library().tracks)
    existing = {t.path: t for t in library_tracks.values()}
    bases = store.source_values(source)

    links = store.source_links(source)
    linked_keys = {track_id: key for key, track_id in links.items()}

    operations: list[ImportOperation] = []
    changes: list[TrackChange] = []
    conflicts: list[FieldConflict] = []
    warnings: list[str] = []
    rebased = 0
    ids: dict[TrackId, TrackId] = {}  # id in the read library -> id in djlib
    for theirs in sorted(read.library.tracks.values(), key=lambda t: t.path):
        values = {name: to_json(getattr(theirs, name)) for name in fields}
        key = read.keys.get(theirs.id)
        # The item's earlier track first, so that a track whose path was fixed in djlib
        # stays linked; then the track at the same path.
        linked = links.get(key) if key is not None else None
        mine = library_tracks.get(linked) if linked is not None else None
        mine = mine or existing.get(theirs.path)
        if mine is None:
            operations.append(AddImportedTrack(theirs, source, values, key))
            changes.append(_change("added", theirs))
            ids[theirs.id] = theirs.id
            library_tracks[theirs.id] = theirs
            continue
        if mine.id in ids.values():
            ids[theirs.id] = mine.id
            warnings.append(f"skipped {theirs.path}: another source item already matched it")
            continue
        ids[theirs.id] = mine.id
        merged, disagreements = _merge(mine, bases.get(mine.id), theirs, fields, adapter.name)
        conflicts.extend(
            FieldConflict(
                track_id=mine.id,
                path=mine.path,
                label=display_name(mine),
                field=d.field,
                library_value=d.library_value,
                file_value=d.source_value,
            )
            for d in disagreements
        )
        library_tracks[mine.id] = merged
        if merged != mine:
            operations.append(UpdateImportedTrack(merged, source, values, key))
            if fields_changed := diff_tracks(mine, merged):
                changes.append(_change("updated", merged, fields_changed))
            else:
                rebased += 1
        elif bases.get(mine.id) != values or (key is not None and linked_keys.get(mine.id) != key):
            operations.append(RecordSourceValues(mine.id, source, values, key))
            rebased += 1

    folder_operation, nodes = _source_folder(
        store, source, adapter, read.library, ids, library_tracks
    )
    if folder_operation is not None:
        operations.append(folder_operation)
    if operations:
        operations.insert(0, RegisterSource(source, now))
    return ImportPlan(
        source=source,
        operations=tuple(operations),
        tracks=tuple(changes),
        nodes=nodes,
        conflicts=tuple(conflicts),
        warnings=(*read.warnings, *warnings, *_missing_files(changes)),
        rebased=rebased,
    )


def _missing_files(changes: list[TrackChange]) -> list[str]:
    """A warning for the added or updated tracks whose files are not on this computer."""
    missing = [c for c in changes if not Path(c.path).exists()]
    if not missing:
        return []
    examples = ", ".join(c.path for c in missing[:5])
    return [
        f"{len(missing)} imported tracks point to files that do not exist on this computer"
        f" (e.g. {examples}); they are imported anyway and can be relocated"
    ]


def _merge(
    mine: Track,
    base: Mapping[str, JSONValue] | None,
    theirs: Track,
    fields: tuple[str, ...],
    adapter: str,
) -> tuple[Track, list[FieldDisagreement]]:
    source_values = {name: getattr(theirs, name) for name in fields}
    changes, disagreements = merge_fields(
        mine, base, source_values, fields, lambda _name, value: to_json(value)
    )
    # The adapter's own unmapped data belongs to the source: it always follows it.
    unmapped = dict(mine.unmapped)
    if adapter in theirs.unmapped:
        unmapped[adapter] = theirs.unmapped[adapter]
    else:
        unmapped.pop(adapter, None)
    if unmapped != dict(mine.unmapped):
        changes["unmapped"] = unmapped
    merged = dataclasses.replace(mine, **changes) if changes else mine
    return merged, disagreements


def _change(
    kind: TrackChangeKind, track: Track, fields: tuple[FieldChange, ...] = ()
) -> TrackChange:
    return TrackChange(
        change=kind,
        track_id=track.id,
        path=track.path,
        label=display_name(track),
        fields=fields,
    )


def _source_folder(
    store: Store,
    source: str,
    adapter: Adapter,
    read: Library,
    ids: Mapping[TrackId, TrackId],
    tracks: Mapping[TrackId, Track],
) -> tuple[ReplaceSourceFolder | None, tuple[NodeChange, ...]]:
    info = store.source(source)
    current = None
    if info is not None and info.root_node_id is not None:
        current_node = store.get_node(info.root_node_id)
        current = current_node if isinstance(current_node, Folder) else None
    if current is None and not read.playlists:
        return None, ()  # a source without playlists, such as beets, gets no folder
    read = _without_own_playlists(store, source, read, current)
    name = current.name if current is not None else _free_name(store, adapter)
    known = {} if current is None else by_path(Library(tracks=tracks, playlists=(current,)))

    def rebuild(node: Node, path: NodePath) -> Node:
        old = known.get(path)
        node_id = old.node.id if old is not None and kind_of(old.node) == kind_of(node) else None
        node_id = node_id or new_node_id()
        if isinstance(node, Folder):
            children = tuple(rebuild(c, (*path, c.name)) for c in node.children)
            return dataclasses.replace(node, id=node_id, children=children)
        if isinstance(node, Playlist):
            entries = tuple(ids[e] for e in node.entries)
            return dataclasses.replace(node, id=node_id, entries=entries)
        return dataclasses.replace(node, id=node_id)

    folder = Folder(
        id=current.id if current is not None else new_node_id(),
        name=name,
        children=tuple(rebuild(c, (name, c.name)) for c in read.playlists),
        unmapped={} if current is None else current.unmapped,
    )
    if folder == current:
        return None, ()
    before = Library(tracks=tracks, playlists=() if current is None else (current,))
    after = Library(tracks=tracks, playlists=(folder,))
    nodes, _, _ = diff_export(before, after, None, _NO_TRACK_DIFF)
    remaining = by_path(after)
    removed = tuple(
        NodeChange(change="removed", path=path, kind=kind_of(placed.node))
        for path, placed in by_path(before).items()
        if path not in remaining
    )
    return ReplaceSourceFolder(source, folder), (*nodes, *removed)


def _without_own_playlists(
    store: Store, source: str, read: Library, folder: Folder | None
) -> Library:
    """``read`` without the playlists djlib exported there from nodes outside ``folder``."""
    inside: set[NodeId] = set()
    pending: list[Node] = [] if folder is None else [folder]
    while pending:
        node = pending.pop()
        inside.add(node.id)
        if isinstance(node, Folder):
            pending.extend(node.children)
    own = {path for node_id, path in store.sync_paths(source).items() if node_id not in inside}
    if not own:
        return read

    def keep(nodes: tuple[Node, ...], path: NodePath) -> tuple[Node, ...]:
        kept: list[Node] = []
        for node in nodes:
            inner = (*path, node.name)
            if inner in own:
                continue
            if isinstance(node, Folder):
                node = dataclasses.replace(node, children=keep(node.children, inner))
            kept.append(node)
        return tuple(kept)

    return dataclasses.replace(read, playlists=keep(read.playlists, ()))


def _free_name(store: Store, adapter: Adapter) -> str:
    """The adapter's display name, numbered when another root node already uses it."""
    base: str = getattr(adapter, "display_name", adapter.name)
    taken = {node.name.casefold() for node in store.children()}
    name, counter = base, 2
    while name.casefold() in taken:
        name, counter = f"{base} ({counter})", counter + 1
    return name
