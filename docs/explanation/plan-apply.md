# Plan, snapshot, apply

tunedex's first promise is that it never breaks your library. Every command that changes something works in the same three steps, and each step has a job in keeping that promise.

## 1. Plan

tunedex reads the current state and computes every change it would make, without writing anything:

- for the library: tracks added, updated, moved, merged or marked missing, and playlists changed;
- for an export: the final content of every file it would write, together with the hash of each file as it is now;
- for [`write-tags`](../guides/write-tags.md): each audio file's fields to write, read fresh from the file;
- for [`rename`](../guides/rename.md): each file's old and new name.

This is what a command prints without `--apply`, and what `--json` returns as a [`tunedex-plan`](../reference/json.md#tunedex-plan). The plan also lists **losses**, which are what the target cannot hold, and **conflicts**, so that you know about them before anything is written.

Imports are only ever read: Mixxx's database, beets' database and your audio files are never written by an import or a scan. Only `write-tags` writes into audio files, `rename` renames them, and `dupes --merge` moves them to the trash, each through its own plan.

## 2. Snapshot

With `--apply`, and after you confirm, tunedex copies what it is about to change into a [snapshot](../guides/snapshots.md):

- the library database, for changes to the library;
- the target files, for an export;
- the tags of the audio files, for `write-tags`: every byte outside the audio stream, so the snapshot stays small;
- the library and the list of old and new names, for `rename`.

No write happens without a snapshot.

## 3. Apply

tunedex then writes, with these checks:

1. **Nothing changed since the plan.** For an export, the hash of each target file must still match the one in the plan. For the library, its revision must be the same. For audio files, their size and modification time, checked again right before each file is written. If something changed, for instance because Mixxx saved its database in between, tunedex stops with `stale_target`.
2. **Atomic writes.** Each file is written to a temporary name next to it and then renamed into place, so a file is never half written. An audio file's copy must have the same audio as the original before it replaces it. Changes to the library run in one database transaction.
3. **Restore on failure.** If anything fails after writing started, tunedex puts the snapshot back and reports `apply_failed`, saying whether the restore worked.

Running a command again after applying it plans nothing: there is nothing left to do.

## Why dry-run by default

Your library holds years of cues, playlists and tag work. A tool that writes first and lets you check afterwards is a tool you can only trust after it has hurt you. In tunedex you see the whole change first, and a snapshot covers the case where you change your mind later.

The confirmation question is the last chance to stop. `--yes` skips it for scripts, which should look at the `--json` plan first. [Using tunedex from another program](../guides/from-another-program.md) shows the flow.
