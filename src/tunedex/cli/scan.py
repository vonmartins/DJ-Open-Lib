"""``tunedex scan``: bring the library in line with a music folder."""

from pathlib import Path
from typing import Annotated

import typer

from tunedex.cli import _options, _paths
from tunedex.cli._flow import reported_errors, run


def scan(
    ctx: typer.Context,
    folder: Annotated[Path, typer.Argument(help="Music folder to scan.", show_default=False)],
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
    _no_color: _options.NoColor = False,
) -> None:
    """Add, update, move and mark missing the tracks of a music folder.

    Tags are read from the files; the files are never changed.

    Example: tunedex scan ~/Music --apply
    """
    with reported_errors(as_json):
        root = _paths.folder(folder)
    run(ctx, lambda engine: engine.plan_scan(root), apply=apply, yes=yes, as_json=as_json)
