"""``tunedex write-tags``: write the library's values into the tags of the tracks' files."""

import typer

from tunedex.cli import _options, _paths
from tunedex.cli._flow import reported_errors, run


def write_tags(
    ctx: typer.Context,
    under: _options.Under = None,
    apply: _options.Apply = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
    _no_color: _options.NoColor = False,
) -> None:
    """Write the library's tags into the audio files, so other apps and players see them.

    Only fields that differ are written: title, artist, album, album artist, genre, year,
    track and disc number, BPM, key, composer, remixer, label, comment, grouping and
    lyricist. Cover art and every other tag stay. MP3, FLAC, WAV and AIFF files are
    written; files changed since the last scan are skipped. A snapshot of the tags
    (target tags) is taken first, so the write can be undone.

    Example: tunedex write-tags --under ~/Music/new --apply
    """
    with reported_errors(as_json):
        folder = _paths.optional_folder(under)
    run(
        ctx,
        lambda engine: engine.plan_write_tags(under=folder),
        apply=apply,
        yes=yes,
        as_json=as_json,
    )
