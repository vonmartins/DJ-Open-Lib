"""``djlib relocate``: point tracks whose files are not on this computer at their files."""

from pathlib import Path
from typing import Annotated

import typer

from djlib.cli import _options
from djlib.cli._flow import fail, run


def relocate(
    ctx: typer.Context,
    folder: Annotated[Path, typer.Argument(help="Folder where the files are now.")],
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Plan new paths under FOLDER for the tracks whose files do not exist here.

    Files are found by name; nothing on disk is moved, renamed or read.
    """
    if not folder.is_dir():
        fail(f"{folder} is not a directory")
    run(ctx, lambda engine: engine.plan_relocate(folder), apply=apply, yes=yes, as_json=as_json)
