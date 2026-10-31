# tunedex

**A free, local-first, scriptable DJ library manager.**

Your music folder, and optionally your [beets](https://beets.io) library, is the source of truth. DJ apps such as Mixxx are targets you sync to safely: every write is planned first, shown as a diff, and backed by a snapshot you can restore.

!!! warning "Pre-alpha"
    tunedex is young. Try it with a scratch home and a test profile of your DJ app before you point it at the library you play from.

## Where to start

<div class="grid cards" markdown>

- **New to tunedex?** [Install it](install.md), then follow the [tutorial](tutorial.md): scan a folder, clean the tags and export to Mixxx in ten minutes.
- **Cleaning up a library?** The guides cover [importing from Mixxx](guides/import-mixxx.md) or [beets](guides/import-beets.md), [fixing tags](guides/fix.md), [enriching them from MusicBrainz](guides/enrich.md) and [merging duplicates](guides/duplicates.md).
- **Building an app or a script on top?** Read [using tunedex from another program](guides/from-another-program.md), then the [JSON formats](reference/json.md) and the [Python API](reference/python-api.md).
- **Looking something up?** Every command and option is in the [command reference](reference/cli.md).

</div>

## What it does

- **Imports** your music folder, Mixxx and beets, read only.
- **Cleans** tags with bundled fixes and your own [rules](reference/rules.md) in YAML.
- **Recognizes** tracks by their sound and takes their tags from MusicBrainz, when you ask it to.
- **Finds and merges duplicates**, keeping the best file and moving the others to the system trash.
- **Finds moved files** after a disk or a folder changes.
- **Exports** playlists to Mixxx and M3U.
- **Undoes** any write: a snapshot is taken before each one.

## Principles

- **Never break your library.** Imports are read-only. Writes need a plan, a snapshot and your confirmation. Dry-run is the default. See [plan, snapshot, apply](explanation/plan-apply.md).
- **Library as code.** Cleanup rules live in YAML you can version with git.
- **Open data.** A [documented SQLite database](explanation/store.md). No accounts, no telemetry, no cloud.
- **Headless first.** Everything works from the command line, with [JSON output](reference/json.md) for other programs.
- **Runs everywhere**: Linux, macOS and Windows.

tunedex is free software under the [GPL-3.0-or-later](https://github.com/vonmartins/tunedex/blob/main/LICENSE) license.
