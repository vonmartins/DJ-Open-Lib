"""``djlib enrich``: tags from MusicBrainz for tracks AcoustID recognizes by their sound."""

from typing import Annotated

import typer

from djlib.cli import _options, _paths
from djlib.cli._flow import home_of, reported_errors, run, stderr_is_interactive
from djlib.cli._progress import StepProgress
from djlib.enrich.cache import Cache
from djlib.enrich.service import Services
from djlib.planning import Engine, Plan


def services(cache: Cache) -> Services:
    """The real services; tests replace this function."""
    return Services.create(cache)


def enrich(
    ctx: typer.Context,
    under: _options.Under = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Ask AcoustID and MusicBrainz again, ignoring the cache."),
    ] = False,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
) -> None:
    """Fill in tags from MusicBrainz for the tracks AcoustID recognizes by their sound.

    Sends each file's fingerprint (from fpcalc) to AcoustID, then asks MusicBrainz. The
    only command that uses the network; answers are cached in the djlib home. Edits made
    in djlib are kept, and audio files are never touched.

    Example: djlib enrich --under ~/Music/new
    """
    with reported_errors(as_json):
        folder = _paths.optional_folder(under)
    home = home_of(ctx)
    # A home without a library has nothing to enrich: do not create one for the cache.
    cache_path = home.cache_file if home.exists else None

    def make_plan(engine: Engine) -> Plan:
        progress = StepProgress() if stderr_is_interactive() else None
        with Cache(cache_path, refresh=refresh) as cache:
            try:
                return engine.plan_enrich(services(cache), under=folder, steps=progress)
            finally:
                if progress is not None:
                    progress.clear()

    run(ctx, make_plan, apply=apply, yes=yes, as_json=as_json)
