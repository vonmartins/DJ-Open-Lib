"""Command-line interface for djlib.

This layer is thin: it parses arguments and calls into the core library.
The core must never import from this package.
"""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from djlib.cli import export, imports, snapshot
from djlib.cli._flow import Home
from djlib.cli._home import default_home
from djlib.cli.scan import scan

app = typer.Typer(
    name="djlib",
    help="Free, local-first, scriptable DJ library manager.",
    add_completion=False,
)
app.command()(scan)
app.add_typer(imports.app, name="import")
app.add_typer(export.app, name="export")
app.add_typer(snapshot.app, name="snapshot")


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
            envvar="DJLIB_HOME",
            help="Directory for the library and the snapshots. Default: the user data directory.",
            show_default=False,
        ),
    ] = None,
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
    ctx.obj = Home((home or default_home()).absolute())
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def main() -> None:
    """Console script entry point."""
    app()
