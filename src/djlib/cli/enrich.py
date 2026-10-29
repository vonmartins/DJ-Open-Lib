"""``djlib enrich``: tags from MusicBrainz for tracks AcoustID recognizes by their sound."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from djlib.cli import _options
from djlib.cli._flow import fail, home_of, run, stderr_is_interactive
from djlib.cli._home import CACHE
from djlib.enrich.cache import Cache
from djlib.enrich.service import Services
from djlib.planning import Engine, Plan


def services(cache: Cache) -> Services:
    """The real services; tests replace this function."""
    return Services.create(cache)


class StepProgress:
    """Shows, on one line of standard error, how many tracks were enriched so far."""

    def __init__(self) -> None:
        self._shown = False

    def __call__(self, done: int, total: int) -> None:
        sys.stderr.write(f"\r\033[KEnriching: {done}/{total} tracks")
        sys.stderr.flush()
        self._shown = True

    def clear(self) -> None:
        if self._shown:
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()
            self._shown = False


def enrich(
    ctx: typer.Context,
    under: Annotated[
        Path | None,
        typer.Option("--under", help="Only the tracks under this folder.", show_default=False),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Ask AcoustID and MusicBrainz again, ignoring the cache."),
    ] = False,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Plan tags from MusicBrainz for the tracks AcoustID recognizes by their sound.

    Sends each file's fingerprint (from fpcalc) to AcoustID, then asks MusicBrainz.

    The only command that uses the network. Answers are cached in the djlib home.

    Edits made in djlib are kept. Audio files are never touched.
    """
    if under is not None and not under.is_dir():
        fail(f"{under} is not a directory")
    home = home_of(ctx)
    # A home without a library has nothing to enrich: do not create one for the cache.
    cache_path = home.path / CACHE if home.database.exists() else None

    def make_plan(engine: Engine) -> Plan:
        progress = StepProgress() if stderr_is_interactive() else None
        with Cache(cache_path, refresh=refresh) as cache:
            try:
                return engine.plan_enrich(services(cache), under=under, steps=progress)
            finally:
                if progress is not None:
                    progress.clear()

    run(ctx, make_plan, apply=apply, yes=yes, as_json=as_json)
