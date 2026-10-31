"""``tunedex rename``: rename the tracks' files from their tags."""

from typing import Annotated

import typer

from tunedex.cli import _options, _paths
from tunedex.cli._flow import home_of, reported_errors, run
from tunedex.home import RULES
from tunedex.planning import PlanError
from tunedex.renaming import DEFAULT_PATTERN, Pattern, PatternError, parse_pattern
from tunedex.rules import ruleset as rulesets


def rename(
    ctx: typer.Context,
    pattern: Annotated[
        str | None,
        typer.Option(
            "--pattern",
            help=f"File name pattern, such as '{{artist}} - {{title}}{{ (remixer remix)}}'."
            f" Default: the rename pattern of {RULES} in the tunedex home, else"
            f" '{DEFAULT_PATTERN}'.",
            show_default=False,
        ),
    ] = None,
    under: _options.Under = None,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
    _no_color: _options.NoColor = False,
) -> None:
    """Rename the tracks' files from their tags, each in its own folder.

    Placeholders are any text field, {year}, {bpm}, {key} and {track_number}; a part in
    braces with text and one field, such as { (remixer remix)}, is left out when the
    field is empty. Names are made safe on every system. Tracks missing a field, and
    names already taken, are skipped: no file is ever overwritten. The library follows
    the new names; other apps that list the files keep the old ones.

    Example: tunedex rename --under ~/Music/dl --pattern "{artist} - {title}"
    """
    with reported_errors(as_json):
        folder = _paths.optional_folder(under)
        chosen = _pattern(ctx, pattern)
    run(
        ctx,
        lambda engine: engine.plan_rename(chosen, under=folder),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )


def _pattern(ctx: typer.Context, pattern: str | None) -> Pattern:
    """``--pattern``, else the rules file's rename pattern, else the default."""
    try:
        if pattern is not None:
            return parse_pattern(pattern)
    except PatternError as error:
        raise PlanError(str(error)) from None
    path = home_of(ctx).rules_file
    configured = rulesets.load(path).rename if path.exists() else None
    return configured or parse_pattern(DEFAULT_PATTERN)
