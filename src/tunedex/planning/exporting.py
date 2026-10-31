"""Exporting to a target that holds a collection: edits made in the target are respected.

Each field a target updates in place is merged three ways, with what tunedex last
imported from or exported to that target as the base. The target plays the protected
side: a field changed there since the base is left as it is, and reported as a
conflict when tunedex's value also differs.
"""

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass

from tunedex.adapters.contract import Capabilities
from tunedex.adapters.losses import display_name
from tunedex.model.encoding import to_json
from tunedex.model.ids import NodeId, TrackId
from tunedex.model.library import Library
from tunedex.model.playlist import Playlist
from tunedex.model.unmapped import JSONValue
from tunedex.planning.importing import merged_fields
from tunedex.planning.model import FieldConflict
from tunedex.planning.tree import NodePath, walk
from tunedex.sources.merge import merge_fields

Bases = Mapping[TrackId, Mapping[str, JSONValue]]


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportMerge:
    library: Library
    """The library to write: matched tracks carry the merged values."""
    conflicts: tuple[FieldConflict, ...]
    conflict_fields: Mapping[TrackId, frozenset[str]]


def merge_export(
    library: Library, current: Library, bases: Bases, capabilities: Capabilities
) -> ExportMerge:
    """Merge ``library`` with what the target holds now (``current``, in library paths)."""
    fields = merged_fields(capabilities, updated=True)
    in_target = {t.path: t for t in current.tracks.values()}
    tracks = dict(library.tracks)
    conflicts: list[FieldConflict] = []
    conflict_fields: dict[TrackId, frozenset[str]] = {}
    for track in library.tracks.values():
        theirs = in_target.get(track.path)
        if theirs is None:
            continue
        ours = {name: getattr(track, name) for name in fields}
        changes, disagreements = merge_fields(
            theirs, bases.get(track.id), ours, fields, lambda _name, value: to_json(value)
        )
        kept = {name: changes.get(name, getattr(theirs, name)) for name in fields}
        merged = dataclasses.replace(track, **kept)
        if merged != track:
            tracks[track.id] = merged
        if disagreements:
            conflict_fields[track.id] = frozenset(d.field for d in disagreements)
            conflicts.extend(
                FieldConflict(
                    track_id=track.id,
                    path=track.path,
                    name=display_name(track),
                    field=d.field,
                    library_value=d.source_value,
                    file_value=d.library_value,
                )
                for d in disagreements
            )
    return ExportMerge(
        library=dataclasses.replace(library, tracks=tracks),
        conflicts=tuple(conflicts),
        conflict_fields=conflict_fields,
    )


def export_bases(
    library: Library,
    view: Library,
    bases: Bases,
    merge: ExportMerge,
    capabilities: Capabilities,
) -> dict[TrackId, dict[str, JSONValue]]:
    """The merge base of every written track: its values as the target holds them.

    Conflict fields keep their earlier base, or none, so the conflict is reported again
    until an import settles it.
    """
    fields = merged_fields(capabilities)
    ids = {t.path: t.id for t in library.tracks.values()}
    result: dict[TrackId, dict[str, JSONValue]] = {}
    for track in view.tracks.values():
        track_id = ids.get(track.path)
        if track_id is None:
            continue
        values = {name: to_json(getattr(track, name)) for name in fields}
        previous = bases.get(track_id, {})
        for name in merge.conflict_fields.get(track_id, ()):
            if name in previous:
                values[name] = previous[name]
            else:
                values.pop(name, None)
        result[track_id] = values
    return result


def target_paths(library: Library, view: Library) -> dict[NodeId, NodePath]:
    """Where the target holds each written playlist of ``library``."""
    known = {p.node.id for p in walk(library)}
    return {
        placed.node.id: placed.path
        for placed in walk(view)
        if isinstance(placed.node, Playlist) and placed.node.id in known
    }
