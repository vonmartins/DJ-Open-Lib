"""Command-line interface for djlib.

This layer is thin: it parses arguments and calls into the core library.
The core must never import from this package.
"""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from djlib.cli import _console, export, imports, snapshot
from djlib.cli.browse import list_tracks, playlists, show
from djlib.cli.dupes import dupes
from djlib.cli.enrich import enrich
from djlib.cli.fix import fix
from djlib.cli.relocate import relocate
from djlib.cli.scan import scan
from djlib.cli.status import status
from djlib.home import Home, resolve_home

LIBRARY, TAGS, APPS, SAFETY = "Library", "Change tags", "Other apps", "Safety"

app = typer.Typer(
    rich_markup_mode="markdown",
    name="djlib",
    help="Free, local-first, scriptable DJ library manager.",
    epilog=(
        "Commands that change something show a plan and write nothing unless --apply is"
        " given. --json prints one JSON document instead. Exit codes: 0 success (also a dry"
        " run or a declined plan), 1 error, 2 wrong usage."
    ),
    add_completion=False,
)
app.command(rich_help_panel=LIBRARY)(status)
app.command("list", rich_help_panel=LIBRARY)(list_tracks)
app.command(rich_help_panel=LIBRARY)(show)
app.command(rich_help_panel=LIBRARY)(playlists)
app.command(rich_help_panel=LIBRARY)(scan)
app.command(rich_help_panel=LIBRARY)(relocate)
app.command(rich_help_panel=TAGS)(fix)
app.command(rich_help_panel=TAGS)(enrich)
app.command(rich_help_panel=TAGS)(dupes)
app.add_typer(imports.app, name="import", rich_help_panel=APPS)
app.add_typer(export.app, name="export", rich_help_panel=APPS)
app.add_typer(snapshot.app, name="snapshot", rich_help_panel=SAFETY)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"djlib {version('djlib')}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    home: Annotated[
        Path | None,
        typer.Option(
            "--home",
            help="Directory for the library and the snapshots. Default: $DJLIB_HOME, else the"
            " user data directory.",
            show_default=False,
        ),
    ] = None,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Print without color. Also: NO_COLOR=1."),
    ] = False,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Free, local-first, scriptable DJ library manager."""
    _console.set_no_color(no_color)
    ctx.obj = Home(resolve_home(home))
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def main() -> None:
    """Console script entry point."""
    app()
