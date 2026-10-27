"""Options shared by the writing commands."""

from typing import Annotated

import typer

Apply = Annotated[bool, typer.Option("--apply", help="Apply the plan (asks for confirmation).")]
Yes = Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")]
Json = Annotated[bool, typer.Option("--json", help="Print only a JSON document on stdout.")]
