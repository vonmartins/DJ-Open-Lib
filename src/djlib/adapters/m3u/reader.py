"""Parsing M3U files and directory trees into the canonical model."""

import dataclasses
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from djlib.adapters.errors import AdapterReadError
from djlib.adapters.pathmap import PathMapping
from djlib.model.ids import TrackId
from djlib.model.library import Library
from djlib.model.paths import normalize_path
from djlib.model.playlist import Folder, Node, Playlist
from djlib.model.track import Track
from djlib.model.unmapped import JSONValue

NAME = "m3u"
EXTENSIONS = frozenset({".m3u", ".m3u8"})
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_ABSOLUTE = re.compile(r"^(/|\\\\|[A-Za-z]:[\\/])")
_DRIVE_IN_URL = re.compile(r"^/[A-Za-z]:")


@dataclass
class ParsedEntry:
    location: str
    duration_s: float | None = None
    display: str | None = None


@dataclass
class ParsedPlaylist:
    entries: list[ParsedEntry] = field(default_factory=list[ParsedEntry])
    # (index of the entry that follows, line); index == len(entries) for trailing lines.
    directives: list[tuple[int, str]] = field(default_factory=list[tuple[int, str]])


def is_playlist_file(path: Path) -> bool:
    return path.suffix.lower() in EXTENSIONS and not path.name.startswith(".")


def parse_text(text: str) -> ParsedPlaylist:
    parsed = ParsedPlaylist()
    pending: tuple[float | None, str | None] | None = None
    for raw in _LINE_BREAK.split(text):
        line = raw.strip()
        if not line:
            continue
        if line.upper() == "#EXTM3U":
            continue
        if line[:8].upper() == "#EXTINF:":
            pending = _parse_extinf(line[8:])
        elif line.startswith("#"):
            parsed.directives.append((len(parsed.entries), line))
        else:
            duration, display = pending or (None, None)
            parsed.entries.append(ParsedEntry(line, duration, display))
            pending = None
    return parsed


def _parse_extinf(value: str) -> tuple[float | None, str | None]:
    head, _, display = value.partition(",")
    tokens = head.split()
    try:
        duration: float | None = float(tokens[0]) if tokens else None
    except ValueError:
        duration = None
    if duration is not None and duration < 0:
        duration = None
    return duration, display.strip() or None


def decode(path: Path, data: bytes, warnings: list[str]) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        if path.suffix.lower() == ".m3u8":
            raise AdapterReadError(path, f"not valid UTF-8 ({error})") from error
    warnings.append(f"{path}: not UTF-8, read as Windows-1252")
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def resolve_entry(entry: str, playlist_dir: Path, mapping: PathMapping) -> str | None:
    """Library path for an entry line, or ``None`` for URLs that are not files."""
    if entry[:5].lower() == "file:":
        parsed = urllib.parse.urlparse(entry)
        path = urllib.parse.unquote(parsed.path)
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            path = f"//{parsed.netloc}{path}"
        elif _DRIVE_IN_URL.match(path):
            path = path[1:]
    elif _URL_SCHEME.match(entry):
        return None
    elif _ABSOLUTE.match(entry):
        path = entry
    else:
        path = f"{normalize_path(str(playlist_dir.absolute()))}/{entry}"
    return mapping.to_library(path)


@dataclass
class TreeReader:
    """Builds one library from a file or directory, sharing tracks between playlists."""

    mapping: PathMapping
    warnings: list[str] = field(default_factory=list[str])
    tracks: dict[str, Track] = field(default_factory=dict[str, Track])

    def read(self, location: Path) -> Library:
        nodes = [self._playlist(location)] if location.is_file() else self._directory(location)
        return Library.build(self.tracks.values(), nodes)

    def _directory(self, directory: Path) -> list[Node]:
        nodes: list[Node] = []
        for entry in sorted(directory.iterdir(), key=lambda p: (p.name.casefold(), p.name)):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                children = self._directory(entry)
                if children:
                    nodes.append(Folder(name=entry.name, children=tuple(children)))
            elif entry.is_file() and is_playlist_file(entry):
                nodes.append(self._playlist(entry))
        return nodes

    def _playlist(self, path: Path) -> Playlist:
        try:
            data = path.read_bytes()
        except OSError as error:
            raise AdapterReadError(path, str(error)) from error
        parsed = parse_text(decode(path, data, self.warnings))

        entries: list[TrackId] = []
        # Positions refer to parsed entries; map them to kept entries as we go.
        kept_index: dict[int, int] = {}
        for index, entry in enumerate(parsed.entries):
            kept_index[index] = len(entries)
            library_path = resolve_entry(entry.location, path.parent, self.mapping)
            if library_path is None:
                self.warnings.append(f"{path}: skipped non-file entry {entry.location}")
                continue
            entries.append(self._track(library_path, entry).id)
        kept_index[len(parsed.entries)] = len(entries)

        directives: list[JSONValue] = []
        for before, line in parsed.directives:
            position = kept_index[before]
            track = str(entries[position]) if position < len(entries) else None
            directives.append({"before": position, "track": track, "line": line})
        unmapped: dict[str, JSONValue] = {NAME: {"directives": directives}} if directives else {}
        return Playlist(name=path.stem, entries=tuple(entries), unmapped=unmapped)

    def _track(self, library_path: str, entry: ParsedEntry) -> Track:
        """The track for ``library_path``; the first ``#EXTINF`` seen for it sets its data."""
        artist, title = None, entry.display
        if entry.display and " - " in entry.display:
            artist, title = (part.strip() or None for part in entry.display.split(" - ", 1))
        duration = None if entry.duration_s is None else round(entry.duration_s * 1_000_000)

        existing = self.tracks.get(library_path)
        if existing is None:
            track = Track(
                path_origin=library_path, artist=artist, title=title, duration_us=duration
            )
        elif existing.title is None and existing.duration_us is None and (title or duration):
            track = dataclasses.replace(existing, artist=artist, title=title, duration_us=duration)
        else:
            return existing
        self.tracks[library_path] = track
        return track
