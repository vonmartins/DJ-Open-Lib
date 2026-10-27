"""``djlib scan``: bring the library in line with a music folder."""

from pathlib import Path
from typing import Annotated

import typer

from djlib.cli import _options
from djlib.cli._flow import fail, run


def scan(
    ctx: typer.Context,
    folder: Annotated[Path, typer.Argument(help="Music folder to scan.")],
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Plan adding, updating, moving and marking missing tracks from FOLDER."""
    if not folder.is_dir():
        fail(f"{folder} is not a directory")
    run(ctx, lambda engine: engine.plan_scan(folder), apply=apply, yes=yes, as_json=as_json)
