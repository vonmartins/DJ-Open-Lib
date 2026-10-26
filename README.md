# djlib

A free, local-first, scriptable DJ library manager.

Your music folder (and optionally your [beets](https://beets.io) library) is the
source of truth. DJ apps such as Traktor, Rekordbox or Mixxx are targets you sync
to safely: every write is planned first, shown as a diff, and backed by a snapshot
you can restore.

> **Status: pre-alpha.** Nothing useful works yet. Do not point it at your real
> DJ library. `djlib` is a working name; the final project name is still open.

## Goals

- **Never break your library.** Imports are read-only. Writes need a plan, a
  snapshot and your confirmation. Dry-run is the default.
- **Library as code.** Cleanup rules, smartlists and field mappings live in YAML
  you can version with git.
- **Open data.** A documented SQLite database. No accounts, no telemetry, no cloud.
- **Headless first.** Everything works from the command line, with JSON output.
- **Runs everywhere**, including Linux.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run djlib --help
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full set of checks and conventions.

## License

[GPL-3.0-or-later](LICENSE).
