"""Command-line interface for djlib.

This layer is thin: it parses arguments and calls into the core library.
The core must never import from this package.
"""

from importlib.metadata import version

import typer

app = typer.Typer(
    name="djlib",
    help="Free, local-first, scriptable DJ library manager.",
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"djlib {version('djlib')}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    _version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Free, local-first, scriptable DJ library manager."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def main() -> None:
    """Console script entry point."""
    app()
