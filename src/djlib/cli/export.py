"""``djlib export``: write the library's playlists to another format."""

from pathlib import Path
from typing import Annotated

import typer

from djlib.adapters.m3u import M3UAdapter
from djlib.cli import _options
from djlib.cli._flow import run

app = typer.Typer(help="Export playlists to another format.", no_args_is_help=True)


@app.command("m3u")
def m3u(
    ctx: typer.Context,
    destination: Annotated[Path, typer.Argument(help="Directory for the .m3u8 files.")],
    playlist: Annotated[
        list[str] | None,
        typer.Option(
            "--playlist", "-p", help="Playlist or folder path such as Techno/Peak; repeatable."
        ),
    ] = None,
    modified: Annotated[
        bool,
        typer.Option(
            "--modified", help="Only playlists changed since the last export to DESTINATION."
        ),
    ] = False,
    relative_paths: Annotated[
        bool,
        typer.Option("--relative-paths", help="Write track paths relative to each playlist file."),
    ] = False,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Plan writing playlists as M3U8 files under DESTINATION."""
    if playlist and modified:
        raise typer.BadParameter("--playlist and --modified cannot be combined")
    adapter = M3UAdapter(relative_paths=relative_paths)
    run(
        ctx,
        lambda engine: engine.plan_export(
            adapter, destination, playlists=playlist or None, modified_only=modified
        ),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )
