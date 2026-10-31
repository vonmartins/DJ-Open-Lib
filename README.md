# tunedex

A free, local-first, scriptable DJ library manager.

**Documentation: [vonmartins.github.io/tunedex](https://vonmartins.github.io/tunedex/)**

Your music folder (and optionally your [beets](https://beets.io) library) is the
source of truth. DJ apps such as Mixxx are targets you sync to safely: every write is
planned first, shown as a diff, and backed by a snapshot you can restore.

> **Status: pre-alpha.** Try it with a scratch home and a test profile of your DJ app
> before you point it at the library you play from.

## What it does

- **Imports** your music folder, Mixxx and beets, read only.
- **Cleans** tags with bundled fixes and your own rules in YAML.
- **Recognizes** tracks by their sound and takes their tags from MusicBrainz, when you
  ask it to.
- **Finds and merges duplicates**, keeping the best file and moving the others to the
  system trash.
- **Writes the cleaned tags into your files**, keeping cover art and the audio intact,
  and **renames files** from their tags.
- **Exports** playlists to Mixxx and M3U.
- **Undoes** any write: a snapshot is taken before each one.

Everything works from the command line, with JSON output and a Python API for other
programs. No accounts, no telemetry, no cloud.

## Install

```sh
uv tool install git+https://github.com/vonmartins/tunedex
```

or `pipx install git+https://github.com/vonmartins/tunedex`. Python 3.11 or later.

## Quick start

```sh
export TUNEDEX_HOME=/tmp/tunedex-try     # a scratch home, to try it safely
tunedex scan ~/Music                   # show what would be added; writes nothing
tunedex scan ~/Music --apply           # apply it, after confirming
tunedex fix                            # show how the tags would be cleaned
tunedex list --where "bpm>=170"
```

Then follow the [tutorial](https://vonmartins.github.io/tunedex/tutorial/).

## Building on tunedex

Every command takes `--json` and prints one documented JSON document; errors have
stable codes. Python programs can `import tunedex`. See
[using tunedex from another program](https://vonmartins.github.io/tunedex/guides/from-another-program/).

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run tunedex --help
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the checks, the conventions and how to
preview the documentation.

## License

[GPL-3.0-or-later](LICENSE).
