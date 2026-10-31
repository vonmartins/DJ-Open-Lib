"""``tunedex fix``: clean the library's tags with the bundled fixes and the user's rules."""

from pathlib import Path
from typing import Annotated

import typer

from tunedex.cli import _options, _paths
from tunedex.cli._flow import home_of, reported_errors, run
from tunedex.home import RULES
from tunedex.rules import ruleset as rulesets


def fix(
    ctx: typer.Context,
    rules: Annotated[
        Path | None,
        typer.Option(
            "--rules",
            help=f"Rules file. Default: {RULES} in the tunedex home if it exists, else the"
            " bundled fixes.",
            show_default=False,
        ),
    ] = None,
    only: Annotated[
        list[str] | None,
        typer.Option(
            "--only",
            help="Only this fix or rule id; repeatable, or separated by commas.",
            show_default=False,
        ),
    ] = None,
    under: _options.Under = None,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Clean the tags of the library's tracks with the bundled fixes and your rules.

    Fixes remove URLs, video ids and odd characters, and move featured artists and
    remixers to their fields. Each change names the fix or rule that made it. Only the
    library changes; audio files are never touched.

    Example: tunedex fix --only remove_urls --under ~/Music/new
    """
    with reported_errors(as_json):
        folder = _paths.optional_folder(under)
        path = _paths.file(rules) if rules else home_of(ctx).rules_file
        chosen = rulesets.load(path) if rules or path.exists() else rulesets.defaults()
        names = [name.strip() for value in only or () for name in value.split(",")]
        if only:
            chosen = chosen.only(name for name in names if name)
    run(
        ctx,
        lambda engine: engine.plan_fix(chosen, under=folder),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )
