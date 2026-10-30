"""``djlib status``: what is in the library, at a glance."""

import json

import typer

from djlib import query
from djlib.cli import _options
from djlib.cli._flow import home_of, reported_errors
from djlib.model.unmapped import JSONValue

STATUS_FORMAT = "djlib-status"
_TIME = "%Y-%m-%d %H:%M UTC"


def status(ctx: typer.Context, as_json: _options.Json = False) -> None:
    """Show a summary of the library: tracks, playlists, sources, snapshots, duplicates.

    Example: djlib status
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
    lines = [f"Home: {home.path}" + ("" if home.exists else "  (no library yet)")]
    tracks = f"Tracks: {summary.tracks}"
    if summary.missing:
        tracks += f" ({summary.missing} missing on this computer)"
    lines.append(tracks)
    lines.append(
        f"Playlists: {summary.playlists}, smartlists: {summary.smartlists},"
        f" folders: {summary.folders}"
    )
    lines.append("Imported from:" + ("" if summary.sources else " nothing yet"))
    lines.extend(f"  {s.name}  {s.imported_at.strftime(_TIME)}" for s in summary.sources)
    lines.append("Last snapshots:" + ("" if summary.snapshots else " none"))
    lines.extend(
        f"  {s.target}  {s.id}  {s.created_at.strftime(_TIME)}  {s.reason or ''}".rstrip()
        for s in summary.snapshots
    )
    groups = summary.duplicate_groups
    if groups:
        noun = "group" if groups == 1 else "groups"
        lines.append(f"Duplicates: {groups} {noun}; see djlib dupes")
    else:
        lines.append("Duplicates: none")
    typer.echo("\n".join(lines))
