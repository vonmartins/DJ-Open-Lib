"""Planning writes of the library's values into the tags of the tracks' files.

Each file is read fresh, because it can differ from the library, and only the fields
whose values differ are written. Files edited since the last scan are never written.
"""

import os
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tunedex.adapters.losses import display_name
from tunedex.model.track import Track
from tunedex.planning.model import FieldChange, TagFile, TrackChange
from tunedex.planning.relocating import report
from tunedex.sources.tags import format_of_extension, read_file
from tunedex.store import Store
from tunedex.tagwrite.regions import WRITABLE_FORMATS, LayoutError, audio_region
from tunedex.tagwrite.writer import WRITTEN_FIELDS, text_of, v24_only_frames


@dataclass(frozen=True, slots=True, kw_only=True)
class TagPlan:
    files: tuple[TagFile, ...]
    changes: tuple[TrackChange, ...]
    warnings: tuple[str, ...]


def plan_write_tags(store: Store, under: str | os.PathLike[str] | None = None) -> TagPlan:
    """The tag writes that bring every file, or those under ``under``, in line with the library."""
    listed = store.list_tracks() if under is None else store.list_tracks_under(os.fspath(under))
    files: list[TagFile] = []
    changes: list[TrackChange] = []
    warnings: list[str] = []
    missing: list[Track] = []
    unscanned: list[Track] = []
    edited: list[Track] = []
    unsupported: defaultdict[str, list[Track]] = defaultdict(list)
    v24: list[Track] = []
    dropped: set[str] = set()

    for track in sorted(listed, key=lambda t: t.path):
        path = Path(track.path_origin)
        state = store.file_state(track.id)
        try:
            stat = path.stat()
        except OSError:
            missing.append(track)
            continue
        if state is None:
            unscanned.append(track)
            continue
        if state.missing or (state.size, state.mtime_ns) != (stat.st_size, stat.st_mtime_ns):
            edited.append(track)
            continue
        read = read_file(path)
        if read.warnings and len(read.values) <= 1:  # not even the tags could be read
            warnings.extend(f"not written: {w}" for w in read.warnings)
            continue
        fields, diffs = diff_tags(track, read.values)
        if not fields:
            continue
        fmt = format_of_extension(track.path_origin)
        if fmt not in WRITABLE_FORMATS:
            unsupported[fmt or "other"].append(track)
            continue
        try:
            region = audio_region(path, fmt)
        except LayoutError as error:
            warnings.append(f"{path}: not written ({error})")
            continue
        if fmt == "mp3" and (lost := v24_only_frames(path)):
            v24.append(track)
            dropped.update(lost)
        files.append(
            TagFile(
                track_id=track.id,
                path=track.path_origin,
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                fields=fields,
                tag_bytes=region.tag_bytes,
            )
        )
        changes.append(
            TrackChange(
                change="updated",
                track_id=track.id,
                path=track.path,
                name=display_name(track),
                fields=tuple(diffs),
            )
        )

    warnings.extend(
        report(edited, "files changed since the last scan were not written; scan first")
    )
    warnings.extend(report(missing, "files are missing and were not written"))
    warnings.extend(report(unscanned, "tracks were never scanned and were not written; scan first"))
    for fmt, tracks in sorted(unsupported.items()):
        name = fmt.upper()
        warnings.extend(
            report(tracks, f"{name} files were not written: {name} files are not written yet")
        )
    if v24:
        frames = ", ".join(sorted(dropped))
        warnings.extend(
            report(
                v24,
                f"files have ID3v2.4 frames that ID3v2.3 cannot hold ({frames});"
                " writing drops them",
            )
        )
    return TagPlan(files=tuple(files), changes=tuple(changes), warnings=tuple(warnings))


def diff_tags(
    track: Track, values: Mapping[str, Any]
) -> tuple[dict[str, str | None], list[FieldChange]]:
    """The fields whose file value differs from the library's: their text, and the change."""
    fields: dict[str, str | None] = {}
    diffs: list[FieldChange] = []
    for name in WRITTEN_FIELDS:
        before, after = values.get(name), getattr(track, name)
        if name == "key":
            if before == after:
                continue
        elif text_of(name, before) == text_of(name, after):
            continue
        fields[name] = text_of(name, after, track.key_original)
        diffs.append(FieldChange(name, before, after))
    return fields, diffs
