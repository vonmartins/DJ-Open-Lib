"""``djlib export``: write the library's playlists to another format."""

from pathlib import Path
from typing import Annotated

import typer

from djlib.adapters.m3u import M3UAdapter
from djlib.adapters.mixxx import MixxxAdapter
from djlib.cli import _options
from djlib.cli._flow import run
from djlib.cli._mixxx import mixxx_database

app = typer.Typer(help="Export the library to another format or app.", no_args_is_help=True)


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
    _check_selection(playlist, modified)
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


@app.command("mixxx")
def mixxx(
    ctx: typer.Context,
    database: Annotated[
        Path | None,
        typer.Argument(
            help="mixxxdb.sqlite or the Mixxx settings directory. Default: Mixxx's own.",
            show_default=False,
        ),
    ] = None,
    playlist: Annotated[
        list[str] | None,
        typer.Option(
            "--playlist", "-p", help="Playlist or folder path such as Techno/Peak; repeatable."
        ),
    ] = None,
    modified: Annotated[
        bool,
        typer.Option("--modified", help="Only playlists changed since the last export there."),
    ] = False,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Plan writing the library to a Mixxx library. Quit Mixxx first.

    Tracks, cues, loops, grids, playlists and crates are written. Fields edited in Mixxx
    since the last import are left as they are and shown as conflicts. Nothing in Mixxx
    is deleted.
    """
    _check_selection(playlist, modified)
    adapter = MixxxAdapter()
    location = mixxx_database(adapter, database)
    run(
        ctx,
        lambda engine: engine.plan_export(
            adapter, location, playlists=playlist or None, modified_only=modified
        ),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )


def _check_selection(playlist: list[str] | None, modified: bool) -> None:
    if playlist and modified:
        raise typer.BadParameter("--playlist and --modified cannot be combined")
