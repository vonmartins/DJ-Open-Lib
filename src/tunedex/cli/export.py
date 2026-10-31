"""``tunedex export``: write the library's playlists to another format."""

from pathlib import Path
from typing import Annotated

import typer

from tunedex.adapters.m3u import M3UAdapter
from tunedex.adapters.mixxx import MixxxAdapter
from tunedex.cli import _options, _paths
from tunedex.cli._flow import reported_errors, run
from tunedex.cli._mixxx import mixxx_database

app = typer.Typer(
    rich_markup_mode="markdown",
    help="Export the library to another format or app.",
    no_args_is_help=True,
)


@app.command("m3u")
def m3u(
    ctx: typer.Context,
    destination: Annotated[
        Path,
        typer.Argument(metavar="FOLDER", help="Folder for the .m3u8 files.", show_default=False),
    ],
    playlist: _options.Playlists = None,
    modified: Annotated[
        bool,
        typer.Option("--modified", help="Only playlists changed since the last export there."),
    ] = False,
    relative_paths: Annotated[
        bool,
        typer.Option("--relative-paths", help="Write track paths relative to each playlist file."),
    ] = False,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Write the library's playlists as M3U8 files under a folder.

    Folders become subfolders. The folder is created when the plan is applied.

    Example: tunedex export m3u ~/Playlists -p Techno --apply
    """
    _check_selection(playlist, modified)
    adapter = M3UAdapter(relative_paths=relative_paths)
    destination = _paths.file(destination)
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
    playlist: _options.Playlists = None,
    modified: Annotated[
        bool,
        typer.Option("--modified", help="Only playlists changed since the last export there."),
    ] = False,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Write the library to a Mixxx library. Quit Mixxx first.

    Tracks, cues, loops, grids, playlists and crates are written. Fields edited in Mixxx
    since the last import are left as they are and shown as conflicts. Nothing in Mixxx
    is deleted.

    Example: tunedex export mixxx --modified --apply
    """
    _check_selection(playlist, modified)
    adapter = MixxxAdapter()
    with reported_errors(as_json):
        location = mixxx_database(adapter, _paths.optional_file(database))
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
