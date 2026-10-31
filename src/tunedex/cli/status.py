"""``tunedex status``: what is in the library, at a glance."""

import json

import typer

from tunedex import query
from tunedex.cli import _console, _options
from tunedex.cli._console import Line
from tunedex.cli._flow import home_of, reported_errors
from tunedex.model.unmapped import JSONValue

STATUS_FORMAT = "tunedex-status"
_TIME = "%Y-%m-%d %H:%M UTC"


def status(
    ctx: typer.Context, as_json: _options.Json = False, _no_color: _options.NoColor = False
) -> None:
    """Show a summary of the library: tracks, playlists, sources, snapshots, duplicates.

    Example: tunedex status
    """
    home = home_of(ctx)
    with reported_errors(as_json), home.engine() as engine:
        summary = query.status(engine.store, home.snapshots)
    if as_json:
        document: dict[str, JSONValue] = {
            "format": STATUS_FORMAT,
            "version": 1,
            "home": str(home.path),
            "library_exists": home.exists,
            "tracks": summary.tracks,
            "missing": summary.missing,
            "playlists": summary.playlists,
            "smartlists": summary.smartlists,
            "folders": summary.folders,
            "sources": [
                {"name": s.name, "imported_at": s.imported_at.isoformat()} for s in summary.sources
            ],
            "snapshots": [
                {
                    "target": s.target,
                    "id": s.id,
                    "created_at": s.created_at.isoformat(),
                    "reason": s.reason,
                }
                for s in summary.snapshots
            ],
            "duplicate_groups": summary.duplicate_groups,
        }
        typer.echo(json.dumps(document, ensure_ascii=False, indent=2))
        return
    lines: list[Line] = [
        (f"Home: {home.path}" + ("" if home.exists else "  (no library yet)"), None)
    ]
    tracks = f"Tracks: {summary.tracks}"
    if summary.missing:
        tracks += f" ({summary.missing} missing on this computer)"
    lines.append((tracks, "missing" if summary.missing else None))
    lines.append(
        (
            f"Playlists: {summary.playlists}, smartlists: {summary.smartlists},"
            f" folders: {summary.folders}",
            None,
        )
    )
    lines.append(("Imported from:" + ("" if summary.sources else " nothing yet"), "heading"))
    sources = [(s.name, s.imported_at.strftime(_TIME)) for s in summary.sources]
    lines.extend((line, None) for line in _console.columns(sources, indent="  "))
    lines.append(("Last snapshots:" + ("" if summary.snapshots else " none"), "heading"))
    snapshots = [
        (s.target, s.id, s.created_at.strftime(_TIME), s.reason or "") for s in summary.snapshots
    ]
    lines.extend((line, None) for line in _console.columns(snapshots, indent="  "))
    groups = summary.duplicate_groups
    if groups:
        noun = "group" if groups == 1 else "groups"
        lines.append((f"Duplicates: {groups} {noun}; see tunedex dupes", "warning"))
    else:
        lines.append(("Duplicates: none", None))
    _console.echo_lines(lines)
