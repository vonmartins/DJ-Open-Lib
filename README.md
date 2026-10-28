# djlib

A free, local-first, scriptable DJ library manager.

Your music folder (and optionally your [beets](https://beets.io) library) is the
source of truth. DJ apps such as Traktor, Rekordbox or Mixxx are targets you sync
to safely: every write is planned first, shown as a diff, and backed by a snapshot
you can restore.

> **Status: pre-alpha.** Only folder scans, Mixxx imports, M3U exports and snapshots
> work so far.
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

### Importing from Mixxx

```sh
uv run djlib --home /tmp/djlib-try import mixxx            # Mixxx's own library, read only
uv run djlib --home /tmp/djlib-try import mixxx ~/mixxx-test/mixxxdb.sqlite --apply
```

- Mixxx's database is only read (from a consistent copy, even while Mixxx runs). Tracks,
  keys, hot cues, the main cue, loops, beat grids, playlists and crates are imported;
  the Auto DJ queue and the history are not.
- Tracks are matched by path. The first import only fills fields that are empty in
  djlib; later imports take changes made in Mixxx unless you edited the same field in
  djlib too, in which case djlib keeps your value and the plan reports a conflict.
- Playlists and crates go to a `Mixxx` folder (`Mixxx/Playlists`, `Mixxx/Crates`)
  that each import replaces; nothing else in djlib is touched.
- To experiment without your real library, start Mixxx with a separate profile:
  `mixxx --settingsPath ~/mixxx-test`.

### Importing from beets

```sh
uv run djlib --home /tmp/djlib-try import beets                          # beets' own library
uv run djlib --home /tmp/djlib-try import beets ~/Music/.beets.db --apply
```

- beets' database and your music files are only read; beets does not need to be
  installed. Every track is imported with its tags (genre, label, key, MusicBrainz and
  Discogs ids, ISRC…); albums do not become playlists.
- Tracks are matched by path the first time, and to the same beets item afterwards, so a
  track whose path you fix in djlib stays linked. Fields edited in djlib win over later
  beets changes, with a conflict in the plan.
- Without a path, djlib looks where beets does: `$BEETSDIR`, then the `library` setting
  of beets' `config.yaml`, then `~/.config/beets/library.db`. Newer beets versions store
  paths relative to the music directory; it comes from `directory` in the same file, or
  `--music-dir`.
- If beets runs on another computer (a server, a NAS), its paths may not exist where
  djlib runs. The plan says how many tracks point to files that are not here; they are
  imported anyway, to be relocated (see below).

### Relocating tracks

```sh
uv run djlib --home /tmp/djlib-try relocate ~/Elements/Music          # show the plan
uv run djlib --home /tmp/djlib-try relocate ~/Elements/Music --apply
```

- For tracks whose files do not exist on this computer (a disk mounted elsewhere, a
  library made on another machine, a renamed folder), djlib looks for the files under
  the folder you name, by file name, and plans their new paths. There is nothing to
  configure, and it is done once.
- When several files have the same name, the one in the same folders as before wins.
  If that does not settle it, the track is left alone and the plan says so. A file
  already used by another track is never taken.
- Only the path changes: cues, playlists and tags stay, and later imports from the same
  beets or Mixxx library keep matching the track. Files on disk are not touched.

### Exporting to Mixxx

Quit Mixxx first: djlib refuses to write while Mixxx runs.

```sh
uv run djlib --home /tmp/djlib-try export mixxx ~/mixxx-test             # show the plan
uv run djlib --home /tmp/djlib-try export mixxx ~/mixxx-test --apply
uv run djlib --home /tmp/djlib-try export mixxx ~/mixxx-test --playlist Techno/Peak
```

- Written: track metadata, BPM and key, hot cues, the main cue, loops, beat grids,
  tracks Mixxx does not have yet, playlists and crates. Everything else in the database
  (analysis data, cover art, ReplayGain, Auto DJ, history) is kept as it is.
- Playlists from the `Mixxx` folder go back to the playlist or crate they came from.
  Other playlists become Mixxx playlists named after their path: `Techno/Peak` is
  written as `Techno / Peak`, and is not imported back as a copy.
- A field edited in Mixxx since the last import is left as Mixxx has it and the plan
  shows a conflict; import first to bring the Mixxx value into djlib.
- Nothing is deleted from Mixxx, and tracks removed from the Mixxx library are not
  brought back. Smartlists, tags and extra memory cues cannot be stored and are listed
  as losses.
- The previous database is kept as a snapshot: `djlib snapshot list` and
  `djlib snapshot restore <target> <id>` put it back (with Mixxx closed).

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
