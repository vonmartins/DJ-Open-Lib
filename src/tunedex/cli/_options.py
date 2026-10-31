"""Options shared by several commands."""

from pathlib import Path
from typing import Annotated

import typer

from tunedex.cli import _console

Apply = Annotated[bool, typer.Option("--apply", help="Apply the plan (asks for confirmation).")]
Yes = Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")]
Json = Annotated[bool, typer.Option("--json", help="Print only a JSON document on stdout.")]
Under = Annotated[
    Path | None,
    typer.Option("--under", help="Only the tracks under this folder.", show_default=False),
]
Playlists = Annotated[
    list[str] | None,
    typer.Option(
        "--playlist",
        "-p",
        help="Playlist or folder path such as Techno/Peak; repeatable.",
        show_default=False,
    ),
]


def _turn_color_off(value: bool) -> None:
    if value:
        _console.set_no_color(True)


# The root's --no-color, also accepted after a command's name.
NoColor = Annotated[
    bool,
    typer.Option(
        "--no-color",
        help="Print without color. Also: NO_COLOR=1.",
        callback=_turn_color_off,
        expose_value=False,
        hidden=True,
    ),
]
