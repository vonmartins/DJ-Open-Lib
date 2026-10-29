"""``djlib import``: bring tracks and playlists from another app into the library."""

from pathlib import Path
from typing import Annotated

import typer

from djlib.adapters.mixxx import MixxxAdapter
from djlib.cli import _options
from djlib.cli._beets import beets_library, default_music_dir
from djlib.cli._flow import fail, run
from djlib.cli._mixxx import default_mixxx_location, mixxx_database
from djlib.sources.beets import BeetsSource

__all__ = ["app", "default_mixxx_location"]

app = typer.Typer(help="Import tracks and playlists from another app.", no_args_is_help=True)

FindIn = Annotated[
    Path | None,
    typer.Option(
        "--find-in",
        help="Look for tracks whose files are not on this computer in this folder;"
        " only the ones found are imported.",
        show_default=False,
    ),
]


def _search_folder(folder: Path | None) -> Path | None:
    if folder is not None and not folder.expanduser().is_dir():
        fail(f"{folder} is not a directory")
    return None if folder is None else folder.expanduser()


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
    """Plan importing a Mixxx library: tracks, cues, loops, grids, playlists and crates.

    Mixxx's files are only read. Playlists go to a "Mixxx" folder in djlib.
    """
    adapter = MixxxAdapter()
    location = mixxx_database(adapter, database)
    folder = _search_folder(find_in)
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
    """Plan importing the tracks of a beets library and their tags.

    beets' database and the music files are only read. Albums do not become playlists.
    """
    source = BeetsSource(music_dir=(music_dir or default_music_dir()).expanduser())
    location = beets_library(source, library)
    folder = _search_folder(find_in)
    run(
        ctx,
        lambda engine: engine.plan_import(source, location, find_in=folder),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )
