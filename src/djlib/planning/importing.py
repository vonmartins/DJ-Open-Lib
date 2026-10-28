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
from djlib.model.ids import TrackId, new_node_id
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


def merged_fields(capabilities: Capabilities) -> tuple[str, ...]:
    """The fields an import from an adapter with ``capabilities`` merges."""
    fields = [name for name in TRACK_FIELDS if name in capabilities.track_fields]
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

    operations: list[ImportOperation] = []
    changes: list[TrackChange] = []
    conflicts: list[FieldConflict] = []
    rebased = 0
    ids: dict[TrackId, TrackId] = {}  # id in the read library -> id in djlib
    for theirs in sorted(read.library.tracks.values(), key=lambda t: t.path):
        values = {name: to_json(getattr(theirs, name)) for name in fields}
        mine = existing.get(theirs.path)
        if mine is None:
            operations.append(AddImportedTrack(theirs, source, values))
            changes.append(_change("added", theirs))
            ids[theirs.id] = theirs.id
            library_tracks[theirs.id] = theirs
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
            operations.append(UpdateImportedTrack(merged, source, values))
            if fields_changed := diff_tracks(mine, merged):
                changes.append(_change("updated", merged, fields_changed))
            else:
                rebased += 1
        elif bases.get(mine.id) != values:
            operations.append(RecordSourceValues(mine.id, source, values))
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
        warnings=read.warnings,
        rebased=rebased,
    )


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


def _free_name(store: Store, adapter: Adapter) -> str:
    """The adapter's display name, numbered when another root node already uses it."""
    base: str = getattr(adapter, "display_name", adapter.name)
    taken = {node.name.casefold() for node in store.children()}
    name, counter = base, 2
    while name.casefold() in taken:
        name, counter = f"{base} ({counter})", counter + 1
    return name
