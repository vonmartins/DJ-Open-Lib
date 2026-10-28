"""Finding the files of tracks that are not on this computer, under a folder the user names.

Tracks are matched by file name, ignoring case and Unicode normalization, with an exact
name preferred. Among files with the same name, the one keeping the most trailing folders
of the old path wins;
a remaining tie is settled by the size a scan recorded, or reported as ambiguous.
Nothing is guessed: a file is never taken twice, nor taken from another track.
"""

import os
import posixpath
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from djlib.adapters.losses import display_name
from djlib.model.ids import TrackId
from djlib.model.track import Track
from djlib.planning.model import TrackChange
from djlib.sources.folder_scan import discover
from djlib.store import Store
from djlib.store.operations import RelocateTrack

_EXAMPLES = 5


@dataclass(frozen=True, slots=True)
class _File:
    path: Path
    normalized: str
    size: int


@dataclass(frozen=True, slots=True, kw_only=True)
class RelocationPlan:
    operations: tuple[RelocateTrack, ...]
    tracks: tuple[TrackChange, ...]
    warnings: tuple[str, ...]


def _fold(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _shared_tail(old: str, new: str) -> int:
    """How many trailing parent folders the two paths have in common."""
    a = reversed(posixpath.dirname(old).split("/"))
    b = reversed(posixpath.dirname(new).split("/"))
    count = 0
    for left, right in zip(a, b, strict=False):
        if _fold(left) != _fold(right) or not left:
            break
        count += 1
    return count


def plan_relocate(store: Store, folder: Path) -> RelocationPlan:
    """Plan new paths under ``folder`` for the tracks whose files do not exist. Changes nothing."""
    tracks = store.list_tracks()
    missing = [t for t in tracks if not Path(t.path_origin).exists()]
    if not missing:
        return RelocationPlan(operations=(), tracks=(), warnings=())

    warnings: list[str] = []
    taken = {t.path for t in tracks}
    index: defaultdict[str, list[_File]] = defaultdict(list)
    for found in discover(folder, warnings):
        if found.normalized not in taken:
            file = _File(found.path, found.normalized, found.size)
            index[_fold(posixpath.basename(found.normalized))].append(file)

    chosen: dict[TrackId, tuple[Track, _File]] = {}
    not_found: list[Track] = []
    ambiguous: list[Track] = []
    for track in sorted(missing, key=lambda t: t.path):
        candidates = index.get(_fold(posixpath.basename(track.path)), [])
        best = _best(store, track, candidates)
        if best is None:
            (ambiguous if len(candidates) > 1 else not_found).append(track)
        else:
            chosen[track.id] = (track, best)
    claims = Counter(file.normalized for _track, file in chosen.values())
    for track_id, (track, file) in list(chosen.items()):
        if claims[file.normalized] > 1:
            del chosen[track_id]
            ambiguous.append(track)

    operations = tuple(RelocateTrack(t.id, os.fspath(f.path)) for t, f in chosen.values())
    changes = tuple(
        TrackChange(
            change="moved",
            track_id=t.id,
            path=f.normalized,
            name=display_name(t),
            old_path=t.path,
        )
        for t, f in chosen.values()
    )
    warnings.extend(_report(not_found, f"missing tracks were not found under {folder}"))
    warnings.extend(
        _report(ambiguous, "missing tracks match several files and were left as they are")
    )
    return RelocationPlan(operations=operations, tracks=changes, warnings=tuple(warnings))


def _best(store: Store, track: Track, candidates: Sequence[_File]) -> _File | None:
    if not candidates:
        return None
    # A file with exactly the old name wins over names that differ only in case.
    name = unicodedata.normalize("NFC", posixpath.basename(track.path))
    exact = [f for f in candidates if posixpath.basename(f.normalized) == name]
    candidates = exact or candidates
    scores = {id(f): _shared_tail(track.path, f.normalized) for f in candidates}
    top = max(scores.values())
    best = [f for f in candidates if scores[id(f)] == top]
    if len(best) > 1:
        state = store.file_state(track.id)
        if state is not None:
            best = [f for f in best if f.size == state.size]
    return best[0] if len(best) == 1 else None


def _report(tracks: Sequence[Track], what: str) -> list[str]:
    if not tracks:
        return []
    examples = ", ".join(t.path for t in sorted(tracks, key=lambda t: t.path)[:_EXAMPLES])
    return [f"{len(tracks)} {what} (e.g. {examples})"]
