"""Options shared by several commands."""

from pathlib import Path
from typing import Annotated

import typer

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
