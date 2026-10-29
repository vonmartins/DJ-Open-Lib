"""``djlib fix``: clean the library's tags with the bundled fixes and the user's rules."""

from pathlib import Path
from typing import Annotated

import typer

from djlib.cli import _options
from djlib.cli._flow import home_of, reported_errors, run
from djlib.cli._home import RULES
from djlib.rules import ruleset as rulesets


def fix(
    ctx: typer.Context,
    rules: Annotated[
        Path | None,
        typer.Option(
            "--rules",
            help=f"Rules file. Default: {RULES} in the djlib home if it exists, else the"
            " bundled fixes.",
            show_default=False,
        ),
    ] = None,
    only: Annotated[
        str | None,
        typer.Option("--only", help="Comma-separated fix names and rule ids to run."),
    ] = None,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Plan cleaning the tags of every track: URLs, video ids, odd characters, featured
    artists, remixers, missing titles... Each change names the fix or rule that made it.

    Only djlib's library changes; audio files are never touched.
    """
    with reported_errors():
        path = rules or home_of(ctx).path / RULES
        chosen = rulesets.load(path) if rules or path.exists() else rulesets.defaults()
        if only:
            chosen = chosen.only(name.strip() for name in only.split(",") if name.strip())
    run(ctx, lambda engine: engine.plan_fix(chosen), apply=apply, yes=yes, as_json=as_json)
