# djlib

A free, local-first, scriptable DJ library manager.

Your music folder (and optionally your [beets](https://beets.io) library) is the
source of truth. DJ apps such as Traktor, Rekordbox or Mixxx are targets you sync
to safely: every write is planned first, shown as a diff, and backed by a snapshot
you can restore.

> **Status: pre-alpha.** Only folder scans, M3U exports and snapshots work so far.
> Do not point it at your real DJ library. `djlib` is a working name; the final
> project name is still open.

## Goals

- **Never break your library.** Imports are read-only. Writes need a plan, a
  snapshot and your confirmation. Dry-run is the default.
- **Library as code.** Cleanup rules, smartlists and field mappings live in YAML
  you can version with git.
- **Open data.** A documented SQLite database. No accounts, no telemetry, no cloud.
- **Headless first.** Everything works from the command line, with JSON output.
- **Runs everywhere**, including Linux.

## Trying it out

Every command that writes prints its plan and writes nothing unless you add
`--apply`, which then asks for confirmation (`--yes` skips the question). Add
`--json` for machine-readable output.

```sh
# Use a scratch home instead of your user data directory (or set DJLIB_HOME).
uv run djlib --home /tmp/djlib-try scan ~/Music          # show what would be added
uv run djlib --home /tmp/djlib-try scan ~/Music --apply  # apply it, after confirming

uv run djlib --home /tmp/djlib-try export m3u /tmp/playlists --apply
uv run djlib --home /tmp/djlib-try export m3u /tmp/playlists --playlist Techno/Peak
uv run djlib --home /tmp/djlib-try export m3u /tmp/playlists --modified

uv run djlib --home /tmp/djlib-try snapshot list
uv run djlib --home /tmp/djlib-try snapshot restore <target> <id>
```

- The home directory holds `library.db` and `snapshots/`. By default it is
  `~/.local/share/djlib` on Linux, `~/Library/Application Support/djlib` on macOS
  and `%LOCALAPPDATA%\djlib` on Windows.
- Scans never modify your audio files. Every apply takes a snapshot first, and a
  failed apply puts the target back as it was.
- Exports never delete anything: playlists that exist only in the target are left
  alone and reported. There is no full sync (mirroring) mode.
- `--modified` exports the playlists changed since the last export to the same
  directory. Changing path mappings needs a normal (full) export.
- Playlists cannot be imported into djlib yet, so exports only contain playlists
  created through the Python API for now.

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
