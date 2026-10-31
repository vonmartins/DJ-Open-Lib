"""Planning renames of the tracks' files from a pattern of fields, inside their folders.

Nothing is ever overwritten: a name already taken, or one two tracks would share, is
skipped with a warning. Names are compared ignoring case and Unicode normalization, as
macOS and Windows do.
"""

import os
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tunedex.adapters.losses import display_name
from tunedex.model.ids import TrackId
from tunedex.model.paths import normalize_path
from tunedex.model.track import Track
from tunedex.planning.model import FileRename, TrackChange
from tunedex.renaming import Missing, Pattern, safe_name
from tunedex.store import Store

_APPS = {"mixxx": "the Mixxx database", "m3u": "the M3U playlists", "beets": "the beets library"}


@dataclass(frozen=True, slots=True, kw_only=True)
class RenamePlan:
    renames: tuple[FileRename, ...]
    changes: tuple[TrackChange, ...]
    warnings: tuple[str, ...]


def _fold(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


@dataclass(frozen=True, slots=True)
class _Candidate:
    track: Track
    old: Path
    new: Path


def plan_renames(
    store: Store, pattern: Pattern, under: str | os.PathLike[str] | None = None
) -> RenamePlan:
    """The renames ``pattern`` gives every track's file, or those under ``under``."""
    listed = store.list_tracks() if under is None else store.list_tracks_under(os.fspath(under))
    warnings: list[str] = []
    candidates: list[_Candidate] = []
    for track in sorted(listed, key=lambda t: t.path):
        old = Path(track.path_origin)
        state = store.file_state(track.id)
        if (state is not None and state.missing) or not old.is_file():
            warnings.append(f"{old}: not renamed, the file is missing")
            continue
        stem = pattern.format(track)
        if isinstance(stem, Missing):
            warnings.append(f"{old}: not renamed, it has no {stem.field}")
            continue
        name = safe_name(stem, old.suffix)
        if name is None:
            warnings.append(f"{old}: not renamed, the pattern gives it an empty name")
            continue
        if unicodedata.normalize("NFC", name) == unicodedata.normalize("NFC", old.name):
            continue
        candidates.append(_Candidate(track, old, old.with_name(name)))

    chosen = _without_collisions(candidates, warnings)
    renames = tuple(FileRename(c.track.id, os.fspath(c.old), os.fspath(c.new)) for c in chosen)
    changes = tuple(
        TrackChange(
            change="moved",
            track_id=c.track.id,
            path=normalize_path(os.fspath(c.new)),
            name=display_name(c.track),
            old_path=c.track.path,
        )
        for c in chosen
    )
    warnings.extend(_other_apps(store.linked_targets(), [c.track.id for c in chosen]))
    return RenamePlan(renames=renames, changes=changes, warnings=tuple(warnings))


def _without_collisions(candidates: list[_Candidate], warnings: list[str]) -> list[_Candidate]:
    by_target: defaultdict[tuple[Path, str], list[_Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_target[candidate.new.parent, _fold(candidate.new.name)].append(candidate)
    listings: dict[Path, defaultdict[str, list[str]]] = {}
    chosen: list[_Candidate] = []
    for (folder, folded), group in by_target.items():
        if len(group) > 1:
            names = ", ".join(str(c.old) for c in group)
            warnings.append(
                f"{names} would all be named {group[0].new.name}; none of them is renamed"
            )
            continue
        (candidate,) = group
        if folder not in listings:
            listings[folder] = defaultdict(list)
            for entry in _listing(folder):
                listings[folder][_fold(entry)].append(entry)
        own = unicodedata.normalize("NFC", candidate.old.name)
        taken = [n for n in listings[folder][folded] if unicodedata.normalize("NFC", n) != own]
        if taken:
            warnings.append(
                f"{candidate.old}: not renamed, {folder / taken[0]} already has that name"
            )
            continue
        chosen.append(candidate)
    return sorted(chosen, key=lambda c: c.track.path)


def _listing(folder: Path) -> list[str]:
    try:
        return [entry.name for entry in folder.iterdir()]
    except OSError:
        return []


def _other_apps(linked: Mapping[TrackId, set[str]], renamed: list[TrackId]) -> list[str]:
    counts: defaultdict[str, int] = defaultdict(int)
    for track_id in renamed:
        for target in linked.get(track_id, ()):
            counts[target] += 1
    warnings: list[str] = []
    for target, count in sorted(counts.items()):
        app = _APPS.get(target.split("-", 1)[0], "the app")
        tracks = "track" if count == 1 else "tracks"
        warnings.append(
            f"{app} {target} still refers to the old names of {count} renamed {tracks};"
            " it will not find them there"
        )
    return warnings
