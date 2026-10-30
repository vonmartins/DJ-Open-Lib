# djlib

A free, local-first, scriptable DJ library manager.

**Documentation: [vonmartins.github.io/DJ-Open-Lib](https://vonmartins.github.io/DJ-Open-Lib/)**

Your music folder (and optionally your [beets](https://beets.io) library) is the
source of truth. DJ apps such as Mixxx are targets you sync to safely: every write is
planned first, shown as a diff, and backed by a snapshot you can restore.

> **Status: pre-alpha.** Try it with a scratch home and a test profile of your DJ app
> before you point it at the library you play from. `djlib` is a working name; the
> final project name is still open.

## What it does

- **Imports** your music folder, Mixxx and beets, read only.
- **Cleans** tags with bundled fixes and your own rules in YAML.
- **Recognizes** tracks by their sound and takes their tags from MusicBrainz, when you
  ask it to.
- **Finds and merges duplicates**, keeping the best file and moving the others to the
  system trash.
- **Exports** playlists to Mixxx and M3U.
- **Undoes** any write: a snapshot is taken before each one.

Everything works from the command line, with JSON output and a Python API for other
programs. No accounts, no telemetry, no cloud.

## Install

```sh
uv tool install git+https://github.com/vonmartins/DJ-Open-Lib
```

or `pipx install git+https://github.com/vonmartins/DJ-Open-Lib`. Python 3.11 or later.

## Quick start

```sh
export DJLIB_HOME=/tmp/djlib-try     # a scratch home, to try it safely
djlib scan ~/Music                   # show what would be added; writes nothing
djlib scan ~/Music --apply           # apply it, after confirming
djlib fix                            # show how the tags would be cleaned
djlib list --where "bpm>=170"
```

Then follow the [tutorial](https://vonmartins.github.io/DJ-Open-Lib/tutorial/).

## Building on djlib

Every command takes `--json` and prints one documented JSON document; errors have
stable codes. Python programs can `import djlib`. See
[using djlib from another program](https://vonmartins.github.io/DJ-Open-Lib/guides/from-another-program/).

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run djlib --help
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the checks, the conventions and how to
preview the documentation.

## License

[GPL-3.0-or-later](LICENSE).
