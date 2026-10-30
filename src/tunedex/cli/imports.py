"""``tunedex import``: bring tracks and playlists from another app into the library."""

from pathlib import Path
from typing import Annotated

import typer

from tunedex.adapters.mixxx import MixxxAdapter
from tunedex.cli import _options, _paths
from tunedex.cli._beets import beets_library, default_music_dir
from tunedex.cli._flow import reported_errors, run
from tunedex.cli._mixxx import default_mixxx_location, mixxx_database
from tunedex.sources.beets import BeetsSource

__all__ = ["app", "default_mixxx_location"]

app = typer.Typer(
    rich_markup_mode="markdown",
    help="Import tracks and playlists from another app.",
    no_args_is_help=True,
)

FindIn = Annotated[
    Path | None,
    typer.Option(
        "--find-in",
        help="Look for tracks whose files are not on this computer in this folder;"
        " only the ones found are imported.",
        show_default=False,
    ),
]


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
    find_in: FindIn = None,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Import a Mixxx library: tracks, cues, loops, grids, playlists and crates.

    Mixxx's files are only read. Its playlists and crates go to a "Mixxx" folder in
    tunedex, which later imports replace.

    Example: tunedex import mixxx --apply
    """
    adapter = MixxxAdapter()
    with reported_errors(as_json):
        location = mixxx_database(adapter, _paths.optional_file(database))
        folder = _paths.optional_folder(find_in)
    run(
        ctx,
        lambda engine: engine.plan_import(adapter, location, find_in=folder),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )


@app.command("beets")
def beets(
    ctx: typer.Context,
    library: Annotated[
        Path | None,
        typer.Argument(
            help="beets' library.db (or its directory). Default: beets' own.",
            show_default=False,
        ),
    ] = None,
    music_dir: Annotated[
        Path | None,
        typer.Option(
            "--music-dir",
            help="beets' music directory, for libraries with relative paths."
            " Default: `directory` in beets' config.yaml, or ~/Music.",
            show_default=False,
        ),
    ] = None,
    find_in: FindIn = None,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Import the tracks of a beets library and their tags.

    beets' database and the music files are only read. Albums do not become playlists.

    Example: tunedex import beets ~/Music/.beets.db --apply
    """
    with reported_errors(as_json):
        source = BeetsSource(music_dir=_paths.optional_file(music_dir) or default_music_dir())
        location = beets_library(source, _paths.optional_file(library))
        folder = _paths.optional_folder(find_in)
    run(
        ctx,
        lambda engine: engine.plan_import(source, location, find_in=folder),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )
