"""Reporting duplicate tracks, and planning their merge into the track kept from each group."""

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from djlib.adapters.losses import display_name
from djlib.duplicates.grouping import find_groups
from djlib.duplicates.merging import merge
from djlib.duplicates.ranking import Facts, rank
from djlib.model.ids import TrackId
from djlib.model.playlist import Folder, Node, Playlist
from djlib.model.track import Track
from djlib.planning.diff import diff_tracks
from djlib.planning.model import FieldChange, TrackChange, TrashFile
from djlib.planning.relocating import report
from djlib.store import Store
from djlib.store.operations import IgnoreDuplicates, LibraryOperation, MergeTracks

GroupKey: TypeAlias = frozenset[TrackId]
Decision: TypeAlias = TrackId | Literal["skip", "ignore"]
"""The track to keep from a group, or leaving it unmerged, or marking it as not duplicates."""

# The apps whose own libraries list a file djlib may trash.
_APPS = {"beets": "beets", "mixxx": "Mixxx"}


@dataclass(frozen=True, slots=True)
class Copy:
    track: Track
    present: bool
    playlists: int


@dataclass(frozen=True, slots=True)
class Group:
    name: str
    copies: tuple[Copy, ...]
    """Best first: the first copy is the suggested one to keep."""
    reason: str
    """Why the first copy is suggested."""

    @property
    def key(self) -> GroupKey:
        return frozenset(c.track.id for c in self.copies)


@dataclass(frozen=True, slots=True, kw_only=True)
class MergePlan:
    operations: tuple[LibraryOperation, ...]
    tracks: tuple[TrackChange, ...]
    trash: tuple[TrashFile, ...]
    warnings: tuple[str, ...]


def find_duplicates(store: Store) -> tuple[Group, ...]:
    """The library's duplicate groups, except those marked as not duplicates. Read-only."""
    library = store.load_library()
    counts = Counter(
        entry for playlist in _playlists(library.playlists) for entry in set(playlist.entries)
    )
    marked = store.not_duplicates()
    groups: list[Group] = []
    for tracks in find_groups(library.tracks.values()):
        key = frozenset(t.id for t in tracks)
        if any(key <= ignored for ignored in marked):
            continue
        facts = {
            t.id: Facts(present=Path(t.path_origin).exists(), playlists=counts[t.id])
            for t in tracks
        }
        ranked = rank(tracks, facts)
        copies = tuple(Copy(t, facts[t.id].present, facts[t.id].playlists) for t in ranked.tracks)
        groups.append(
            Group(name=display_name(ranked.tracks[0]), copies=copies, reason=ranked.reason)
        )
    return tuple(sorted(groups, key=lambda g: (g.name.casefold(), g.copies[0].track.path)))


def plan_merge(
    store: Store,
    decisions: Mapping[GroupKey, Decision] | None = None,
    *,
    keep_files: bool = False,
) -> MergePlan:
    """Merge each group into its suggested track, or as ``decisions`` say. Changes nothing."""
    decisions = decisions or {}
    operations: list[LibraryOperation] = []
    changes: list[TrackChange] = []
    trash: list[TrashFile] = []
    in_apps: dict[str, list[Track]] = {}
    for group in find_duplicates(store):
        decision = decisions.get(group.key)
        if decision == "skip":
            continue
        if decision == "ignore":
            operations.append(IgnoreDuplicates(group.key))
            continue
        tracks = [c.track for c in group.copies]
        if decision is not None:
            tracks.sort(key=lambda t: t.id != decision)
        best, others = tracks[0], tracks[1:]
        keeper = merge(best, others)
        operations.append(MergeTracks(keeper, tuple(t.id for t in others)))
        if keeper != best:
            fields = tuple(
                FieldChange(f.field, f.before, f.after, "merge") for f in diff_tracks(best, keeper)
            )
            changes.append(_change("updated", best, fields=fields))
        for other in others:
            changes.append(_change("merged", other, merged_into=best.path))
            for source, app in _APPS.items():
                if source in other.unmapped:
                    in_apps.setdefault(app, []).append(other)
            if not keep_files and (file := _trash_file(other)) is not None:
                trash.append(file)
    warnings: list[str] = []
    if trash:
        for app, tracks in in_apps.items():
            warnings.extend(
                report(
                    tracks,
                    f"files to trash are in your {app} library, which will list them as missing",
                )
            )
    return MergePlan(
        operations=tuple(operations),
        tracks=tuple(changes),
        trash=tuple(trash),
        warnings=tuple(warnings),
    )


def _trash_file(track: Track) -> TrashFile | None:
    try:
        stat = Path(track.path_origin).stat()
    except OSError:
        return None  # nothing to trash: the file is not on this computer
    return TrashFile(track.path_origin, stat.st_size, stat.st_mtime_ns)


def _change(
    kind: Literal["updated", "merged"],
    track: Track,
    *,
    fields: tuple[FieldChange, ...] = (),
    merged_into: str | None = None,
) -> TrackChange:
    return TrackChange(
        change=kind,
        track_id=track.id,
        path=track.path,
        name=display_name(track),
        fields=fields,
        merged_into=merged_into,
    )


def _playlists(nodes: Sequence[Node]) -> Iterator[Playlist]:
    for node in nodes:
        if isinstance(node, Playlist):
            yield node
        elif isinstance(node, Folder):
            yield from _playlists(node.children)
