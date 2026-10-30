"""Planning M3U8 files for the playlists of a library."""

import hashlib
import posixpath
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from tunedex.adapters.contract import Capabilities, FileChange, WriteOptions, WritePlan
from tunedex.adapters.losses import LossCollector, compute_losses, display_name
from tunedex.adapters.m3u.names import sanitize, unique
from tunedex.adapters.m3u.reader import NAME
from tunedex.adapters.pathmap import PathMapping
from tunedex.model.ids import NodeId, TrackId
from tunedex.model.library import Library
from tunedex.model.paths import normalize_path
from tunedex.model.playlist import Folder, Node, Playlist
from tunedex.model.track import Track

CAPABILITIES = Capabilities(
    track_fields=frozenset({"title", "artist", "duration_us"}), folders=True
)
_DRIVE = re.compile(r"^[A-Za-z]:/")
_LINE_BREAKS = re.compile(r"[\r\n]+")


@dataclass(frozen=True, slots=True)
class _Planned:
    node: Node
    directory: tuple[str, ...]
    file_name: str | None  # only for playlists


def plan_write(
    library: Library, location: Path, options: WriteOptions, *, relative_paths: bool
) -> WritePlan:
    losses = LossCollector()
    warnings: list[str] = []
    planned = list(_layout(library.playlists, (), losses))
    selected = [p for p in planned if _is_selected(p, library, options.selection)]

    changes: list[FileChange] = []
    written_tracks: list[TrackId] = []
    for item in selected:
        if not isinstance(item.node, Playlist) or item.file_name is None:
            continue
        path = location.joinpath(*item.directory, item.file_name)
        content, dropped = _content(item.node, library.tracks, path, options.path_mapping,
                                    relative_paths, warnings)  # fmt: skip
        if dropped:
            losses.add(
                "directives-dropped",
                "kept M3U lines whose entry changed were dropped",
                item.node.name,
            )
        written_tracks.extend(item.node.entries)
        change = _change(path, content, item.node)
        if change is not None:
            changes.append(change)

    for track_id in dict.fromkeys(written_tracks):
        track = library.tracks[track_id]
        if track.duration_us is not None and track.duration_us % 1_000_000:
            losses.add(
                "duration-rounded", "durations are rounded to whole seconds", display_name(track)
            )
    compute_losses(library, written_tracks, [p.node for p in selected], CAPABILITIES, NAME, losses)
    return WritePlan(
        adapter=NAME,
        location=location,
        changes=tuple(changes),
        losses=losses.losses(),
        warnings=tuple(warnings),
    )


def _layout(
    nodes: tuple[Node, ...], directory: tuple[str, ...], losses: LossCollector
) -> Iterator[_Planned]:
    """Assign directories and file names to every node, in tree order."""
    folder_names: set[str] = set()
    file_names: set[str] = set()
    for node in nodes:
        if isinstance(node, Folder):
            name = unique(sanitize(node.name), folder_names)
            _report_rename(node.name, name, losses)
            yield _Planned(node, directory, None)
            yield from _layout(node.children, (*directory, name), losses)
        elif isinstance(node, Playlist):
            name = unique(sanitize(node.name), file_names)
            _report_rename(node.name, name, losses)
            yield _Planned(node, directory, f"{name}.m3u8")
        else:
            yield _Planned(node, directory, None)


def _report_rename(original: str, chosen: str, losses: LossCollector) -> None:
    if chosen != original:
        losses.add("renamed", "names were changed to be valid file names", f"{original} → {chosen}")


def _is_selected(item: _Planned, library: Library, selection: frozenset[NodeId] | None) -> bool:
    if selection is None:
        return True
    return item.node.id in selection or bool(_ancestors(library, item.node.id) & selection)


def _ancestors(library: Library, node_id: NodeId) -> set[NodeId]:
    parents = {node.id: parent for parent, _index, node in library.walk()}
    result: set[NodeId] = set()
    current = parents.get(node_id)
    while current is not None:
        result.add(current)
        current = parents.get(current)
    return result


def _content(
    playlist: Playlist,
    tracks: Mapping[TrackId, Track],
    path: Path,
    mapping: PathMapping,
    relative_paths: bool,
    warnings: list[str],
) -> tuple[bytes, int]:
    """File bytes for ``playlist`` and the number of kept directives that were dropped."""
    directives = _directives(playlist)
    playlist_dir = posixpath.dirname(normalize_path(str(path.absolute())))
    lines = ["#EXTM3U"]
    dropped = 0
    count = len(playlist.entries)
    for index, track_id in enumerate(playlist.entries):
        for before, track, line in directives:
            if before == index:
                if track == str(track_id):
                    lines.append(line)
                else:
                    dropped += 1
        entry = tracks[track_id]
        lines.append(f"#EXTINF:{_seconds(entry)},{_LINE_BREAKS.sub(' ', display_name(entry))}")
        lines.append(_entry_path(entry, playlist_dir, mapping, relative_paths, warnings))
    for before, _track, line in directives:
        if before == count:
            lines.append(line)
        elif before > count:
            dropped += 1
    return ("\n".join(lines) + "\n").encode("utf-8"), dropped


def _directives(playlist: Playlist) -> list[tuple[int, str | None, str]]:
    kept = playlist.unmapped.get(NAME)
    raw = kept.get("directives") if isinstance(kept, dict) else None
    result: list[tuple[int, str | None, str]] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            before, track, line = item.get("before"), item.get("track"), item.get("line")
            if (
                isinstance(before, int)
                and isinstance(line, str)
                and (track is None or isinstance(track, str))
            ):
                result.append((before, track, line))
    return result


def _seconds(track: Track) -> int:
    return -1 if track.duration_us is None else round(track.duration_us / 1_000_000)


def _entry_path(
    track: Track, playlist_dir: str, mapping: PathMapping, relative: bool, warnings: list[str]
) -> str:
    target = mapping.to_target(track.path)
    if relative:
        relative_path = _relative(target, playlist_dir)
        if relative_path is not None:
            return relative_path
        warnings.append(f"no relative path from {playlist_dir} to {target}; wrote it absolute")
    return target.replace("/", "\\") if _DRIVE.match(target) else target


def _relative(target: str, directory: str) -> str | None:
    if _DRIVE.match(target) and _DRIVE.match(directory):
        if target[0].upper() != directory[0].upper():
            return None
        return posixpath.relpath(target[2:], directory[2:]).replace("/", "\\")
    if target.startswith("/") and not target.startswith("//") and directory.startswith("/"):
        return posixpath.relpath(target, directory)
    return None


def _change(path: Path, content: bytes, playlist: Playlist) -> FileChange | None:
    base: str | None = None
    if path.is_file():
        current = path.read_bytes()
        if current == content:
            return None
        base = hashlib.sha256(current).hexdigest()
    verb = "create" if base is None else "update"
    return FileChange(
        path=path,
        content=content,
        base_sha256=base,
        description=f"{verb} playlist {playlist.name!r} ({len(playlist.entries)} entries)",
    )
