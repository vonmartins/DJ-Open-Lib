"""``djlib list``, ``djlib show`` and ``djlib playlists``: look at the library, change nothing."""

import dataclasses
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from djlib import query
from djlib.adapters.losses import display_name
from djlib.cli import _console, _options, _paths
from djlib.cli._console import Line
from djlib.cli._flow import home_of, reported_errors
from djlib.model.encoding import to_json
from djlib.model.paths import normalize_path
from djlib.model.track import Track
from djlib.model.unmapped import JSONValue
from djlib.planning.render import bpm_text, text_value
from djlib.store import NotFoundError

TRACKS_FORMAT = "djlib-tracks"
TRACK_FORMAT = "djlib-track"
PLAYLISTS_FORMAT = "djlib-playlists"
# Fields shown elsewhere in the track view, or not meant for people.
_NOT_LISTED = frozenset({"id", "path", "path_origin", "cues", "beatgrid", "unmapped"})


def list_tracks(
    ctx: typer.Context,
    where: Annotated[
        list[str] | None,
        typer.Option(
            "--where",
            "-w",
            help="Only tracks where FIELD OP VALUE holds, such as bpm>=170 or title~remix."
            " Operators: = != ~ !~ > >= < <=. Repeatable; all must hold.",
            show_default=False,
        ),
    ] = None,
    under: _options.Under = None,
    playlist: _options.Playlists = None,
    missing: Annotated[
        bool, typer.Option("--missing", help="Only tracks whose file is not on this computer.")
    ] = False,
    as_json: _options.Json = False,
) -> None:
    """List the library's tracks, one per line, by artist and title.

    Example: djlib list --where "genre=Techno" --where "bpm>130"
    """
    with reported_errors(as_json):
        folder = _paths.optional_folder(under)
        conditions = [query.parse_where(text) for text in where or ()]
        with home_of(ctx).engine() as engine:
            tracks = query.select(
                engine.store,
                where=conditions,
                under=folder,
                playlists=playlist or (),
                missing=missing,
            )
    if as_json:
        document: dict[str, JSONValue] = {
            "format": TRACKS_FORMAT,
            "version": 1,
            "tracks": [to_json(t) for t in tracks],
        }
        typer.echo(json.dumps(document, ensure_ascii=False, indent=2))
        return
    _console.echo_lines(_track_table(tracks))


def _track_table(tracks: Sequence[Track]) -> list[Line]:
    if not tracks:
        return [("No tracks.", None)]
    folder = common_folder([t.path for t in tracks])
    skip = 0 if folder is None else len(folder) + 1
    rows = [
        (
            _cut(t.artist or "", 28),
            _cut(t.title or Path(t.path).name, 40),
            bpm_text(t.bpm) if t.bpm else "",
            t.key.open_key() if t.key else "",
            text_value("duration_us", t.duration_us) if t.duration_us else "",
            t.path[skip:] if folder else home_short(t.path),
        )
        for t in tracks
    ]
    header = ("ARTIST", "TITLE", "BPM", "KEY", "TIME", "PATH")
    widths = [max(len(row[i]) for row in (header, *rows)) for i in range(5)]
    right = (False, False, True, True, True)
    lines = [
        "  ".join(
            [
                *(
                    cell.rjust(widths[i]) if right[i] else cell.ljust(widths[i])
                    for i, cell in enumerate(row[:5])
                ),
                row[5],
            ]
        )
        for row in (header, *rows)
    ]
    noun = "track" if len(tracks) == 1 else "tracks"
    where = "" if folder is None else f" in {home_short(folder)}/"
    return [
        (lines[0], "header"),
        *((line, None) for line in lines[1:]),
        (f"{len(tracks)} {noun}{where}", "notice"),
    ]


def common_folder(paths: Sequence[str]) -> str | None:
    """The deepest folder holding every path, or None when only a drive root does.

    Paths are normalized, with ``/`` on every system.
    """
    folders = [path.split("/")[:-1] for path in paths]
    common: list[str] = []
    for parts in zip(*folders, strict=False):
        if any(part != parts[0] for part in parts):
            break
        common.append(parts[0])
    # ["", "music"] is /music; ["C:", "Music"] is C:/Music; [""] and ["C:"] are roots.
    return "/".join(common) if len(common) >= 2 else None


def home_short(path: str) -> str:
    """``path`` with ``~`` for the user's home directory."""
    home = normalize_path(str(Path.home()))
    if path == home or path.startswith(home + "/"):
        return "~" + path[len(home) :]
    return path


def _cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def show(
    ctx: typer.Context,
    track: Annotated[
        str,
        typer.Argument(
            metavar="TRACK", help="Path of the track's file, or its id.", show_default=False
        ),
    ],
    as_json: _options.Json = False,
) -> None:
    """Show everything djlib knows about one track.

    Its tags, cues, loops, beat grid, playlists and the apps it was imported from.

    Example: djlib show ~/Music/techno/a.flac
    """
    with reported_errors(as_json), home_of(ctx).engine() as engine:
        try:
            view = query.track_view(engine.store, track)
        except NotFoundError:
            view = query.track_view(engine.store, str(_paths.file(Path(track))))
    if as_json:
        document: dict[str, JSONValue] = {
            "format": TRACK_FORMAT,
            "version": 1,
            "track": to_json(view.track),
            "present": view.present,
            "playlists": list(view.playlists),
            "sources": list(view.sources),
        }
        typer.echo(json.dumps(document, ensure_ascii=False, indent=2))
        return
    _console.echo_lines(_track_text(view))


def _track_text(view: query.TrackView) -> list[Line]:
    track = view.track
    path = f"  {'path':<14} {track.path_origin}"
    lines: list[Line] = [
        (display_name(track), "heading"),
        (path, None) if view.present else (f"{path}  (missing on this computer)", "missing"),
        (f"  {'id':<14} {track.id}", None),
    ]
    for field in dataclasses.fields(track):
        value = getattr(track, field.name)
        if field.name in _NOT_LISTED or value is None or value in ("", ()):
            continue
        shown = value if isinstance(value, str) else text_value(field.name, value)
        lines.append((f"  {field.name.removesuffix('_us'):<14} {shown}", None))
    if track.cues:
        lines.append(("Cues:", "heading"))
        for cue in sorted(track.cues, key=lambda c: c.start_us):
            at = text_value("start_us", cue.start_us)
            if cue.end_us is not None:
                at += f"-{text_value('end_us', cue.end_us)}"
            slot = "" if cue.slot is None else f" {cue.slot + 1}"
            lines.append((f"  {cue.kind.value}{slot:<3} {at:<11} {cue.name or ''}".rstrip(), None))
    if track.beatgrid is not None:
        first = track.beatgrid.markers[0]
        markers = len(track.beatgrid.markers)
        noun = "marker" if markers == 1 else "markers"
        lines.append((f"Beat grid: {markers} {noun}, from {bpm_text(first.bpm)} BPM", None))
    lines.append((f"Playlists: {', '.join(view.playlists) or 'none'}", None))
    lines.append((f"Imported from: {', '.join(view.sources) or 'none'}", None))
    return lines


def playlists(ctx: typer.Context, as_json: _options.Json = False) -> None:
    """Show the playlist tree, with the number of tracks of each playlist.

    Example: djlib playlists
    """
    with reported_errors(as_json), home_of(ctx).engine() as engine:
        tree = query.playlist_tree(engine.store)
    if as_json:
        document: dict[str, JSONValue] = {
            "format": PLAYLISTS_FORMAT,
            "version": 1,
            "nodes": [to_json(node) for node in tree],
        }
        typer.echo(json.dumps(document, ensure_ascii=False, indent=2))
        return
    if not tree:
        _console.echo("No playlists.")
        return
    lines: list[Line] = []
    for node in tree:
        indent = "  " * node.depth
        if node.tracks is None:
            lines.append((f"{indent}{node.name}/", "folder"))
            continue
        noun = "track" if node.tracks == 1 else "tracks"
        kind = "smartlist, " if node.kind == "smartlist" else ""
        lines.append((f"{indent}{node.name}  ({kind}{node.tracks} {noun})", None))
    _console.echo_lines(lines)
