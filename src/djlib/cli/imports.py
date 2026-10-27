"""``djlib import``: bring tracks and playlists from another app into the library."""

import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from djlib.adapters.mixxx import MixxxAdapter
from djlib.cli import _options
from djlib.cli._flow import fail, run

app = typer.Typer(help="Import tracks and playlists from another app.", no_args_is_help=True)


def default_mixxx_location() -> Path:
    """Mixxx's settings directory, which holds ``mixxxdb.sqlite``."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "Mixxx"
    if sys.platform == "darwin":
        sandboxed = (
            Path.home() / "Library" / "Containers" / "org.mixxx.mixxx" / "Data" / "Library"
            / "Application Support" / "Mixxx"
        )  # fmt: skip
        legacy = Path.home() / "Library" / "Application Support" / "Mixxx"
        return sandboxed if sandboxed.exists() or not legacy.exists() else legacy
    return Path.home() / ".mixxx"


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
    location = database or default_mixxx_location()
    adapter = MixxxAdapter()
    detection = adapter.detect(location)
    if not detection.matches:
        fail(f"no Mixxx library at {location}: {detection.reason}")
    run(
        ctx,
        lambda engine: engine.plan_import(adapter, location),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )
