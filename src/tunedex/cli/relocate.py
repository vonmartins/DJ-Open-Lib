"""``tunedex relocate``: point tracks whose files are not on this computer at their files."""

from pathlib import Path
from typing import Annotated

import typer

from tunedex.cli import _options, _paths
from tunedex.cli._flow import reported_errors, run


def relocate(
    ctx: typer.Context,
    folder: Annotated[
        Path, typer.Argument(help="Folder where the files are now.", show_default=False)
    ],
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
    _no_color: _options.NoColor = False,
) -> None:
    """Find, under a folder, the files of the tracks that are missing on this computer.

    Files are found by name; nothing on disk is moved, renamed or read.

    Example: tunedex relocate /mnt/usb/Music --apply
    """
    with reported_errors(as_json):
        root = _paths.folder(folder)
    run(ctx, lambda engine: engine.plan_relocate(root), apply=apply, yes=yes, as_json=as_json)
