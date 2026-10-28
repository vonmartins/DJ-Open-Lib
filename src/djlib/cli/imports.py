"""``djlib import``: bring tracks and playlists from another app into the library."""

from pathlib import Path
from typing import Annotated

import typer

from djlib.adapters.mixxx import MixxxAdapter
from djlib.cli import _options
from djlib.cli._flow import run
from djlib.cli._mixxx import default_mixxx_location, mixxx_database

__all__ = ["app", "default_mixxx_location"]

app = typer.Typer(help="Import tracks and playlists from another app.", no_args_is_help=True)


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
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Plan importing a Mixxx library: tracks, cues, loops, grids, playlists and crates.

    Mixxx's files are only read. Playlists go to a "Mixxx" folder in djlib.
    """
    adapter = MixxxAdapter()
    location = mixxx_database(adapter, database)
    run(
        ctx,
        lambda engine: engine.plan_import(adapter, location),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )
