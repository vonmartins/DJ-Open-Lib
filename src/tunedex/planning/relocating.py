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
from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass
from pathlib import Path

from tunedex.adapters.losses import display_name
from tunedex.model.ids import TrackId
from tunedex.model.track import Track
from tunedex.planning.model import TrackChange
from tunedex.sources.folder_scan import discover
from tunedex.store import Store
from tunedex.store.operations import RelocateTrack

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


Progress = Callable[[Path, int], None]
"""Told the folder being walked and how many audio files were seen so far."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Found:
    chosen: dict[TrackId, tuple[Track, Path, str]]
    """Track id -> (track, file path, normalized file path)."""
    not_found: list[Track]
    ambiguous: list[Track]
    warnings: list[str]


def find_files(
    folder: Path,
    tracks: Sequence[Track],
    *,
    exclude: Set[str] = frozenset(),
    known_size: Callable[[Track], int | None] = lambda _track: None,
    progress: Progress | None = None,
) -> Found:
    """Find the file of each of ``tracks`` under ``folder``; files in ``exclude`` are never used."""
    warnings: list[str] = []
    if not tracks:
        return Found(chosen={}, not_found=[], ambiguous=[], warnings=warnings)
    index: defaultdict[str, list[_File]] = defaultdict(list)
    for found in discover(folder, warnings, progress=_for_folder(progress, folder)):
        if found.normalized not in exclude:
            file = _File(found.path, found.normalized, found.size)
            index[_fold(posixpath.basename(found.normalized))].append(file)

    chosen: dict[TrackId, tuple[Track, _File]] = {}
    not_found: list[Track] = []
    ambiguous: list[Track] = []
    for track in sorted(tracks, key=lambda t: t.path):
        candidates = index.get(_fold(posixpath.basename(track.path)), [])
        best = _best(track, candidates, known_size)
        if best is None:
            (ambiguous if len(candidates) > 1 else not_found).append(track)
        else:
            chosen[track.id] = (track, best)
    claims = Counter(file.normalized for _track, file in chosen.values())
    for track_id, (track, file) in list(chosen.items()):
        if claims[file.normalized] > 1:
            del chosen[track_id]
            ambiguous.append(track)
    return Found(
        chosen={i: (t, f.path, f.normalized) for i, (t, f) in chosen.items()},
        not_found=not_found,
        ambiguous=ambiguous,
        warnings=warnings,
    )


def _for_folder(progress: Progress | None, folder: Path) -> Callable[[int], None] | None:
    if progress is None:
        return None
    report_progress = progress

    def count(seen: int) -> None:
        report_progress(folder, seen)

    return count


def plan_relocate(
    store: Store, folder: Path, *, progress: Progress | None = None
) -> RelocationPlan:
    """Plan new paths under ``folder`` for the tracks whose files do not exist. Changes nothing."""
    tracks = store.list_tracks()
    missing = [t for t in tracks if not Path(t.path_origin).exists()]
    if not missing:
        return RelocationPlan(operations=(), tracks=(), warnings=())

    def known_size(track: Track) -> int | None:
        state = store.file_state(track.id)
        return None if state is None else state.size

    found = find_files(
        folder,
        missing,
        exclude={t.path for t in tracks},
        known_size=known_size,
        progress=progress,
    )
    chosen = found.chosen.values()
    operations = tuple(RelocateTrack(t.id, os.fspath(path)) for t, path, _ in chosen)
    changes = tuple(
        TrackChange(
            change="moved",
            track_id=t.id,
            path=normalized,
            name=display_name(t),
            old_path=t.path,
        )
        for t, _path, normalized in chosen
    )
    warnings = [*found.warnings]
    warnings.extend(report(found.not_found, f"missing tracks were not found under {folder}"))
    warnings.extend(
        report(found.ambiguous, "missing tracks match several files and were left as they are")
    )
    return RelocationPlan(operations=operations, tracks=changes, warnings=tuple(warnings))


def _best(
    track: Track, candidates: Sequence[_File], known_size: Callable[[Track], int | None]
) -> _File | None:
    if not candidates:
        return None
    # A file with exactly the old name wins over names that differ only in case.
    name = unicodedata.normalize("NFC", posixpath.basename(track.path))
    exact = [f for f in candidates if posixpath.basename(f.normalized) == name]
    candidates = exact or candidates
    scores = {id(f): _shared_tail(track.path, f.normalized) for f in candidates}
    top = max(scores.values())
    best = [f for f in candidates if scores[id(f)] == top]
    if len(best) > 1 and (size := known_size(track)) is not None:
        best = [f for f in best if f.size == size]
    return best[0] if len(best) == 1 else None


def report(tracks: Sequence[Track], what: str) -> list[str]:
    if not tracks:
        return []
    examples = ", ".join(t.path for t in sorted(tracks, key=lambda t: t.path)[:_EXAMPLES])
    return [f"{len(tracks)} {what} (e.g. {examples})"]
