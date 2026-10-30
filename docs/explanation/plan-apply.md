# Plan, snapshot, apply

djlib's first promise is that it never breaks your library. Every command that changes something works in the same three steps, and each step has a job in keeping that promise.

## 1. Plan

djlib reads the current state and computes every change it would make, without writing anything:

- for the library: tracks added, updated, moved, merged or marked missing, and playlists changed;
- for an export: the final content of every file it would write, together with the hash of each file as it is now.

This is what a command prints without `--apply`, and what `--json` returns as a [`djlib-plan`](../reference/json.md#djlib-plan). The plan also lists **losses**, which are what the target cannot hold, and **conflicts**, so that you know about them before anything is written.

Imports are only ever read: Mixxx's database, beets' database and your audio files are never written by an import or a scan.

## 2. Snapshot

With `--apply`, and after you confirm, djlib copies what it is about to change into a [snapshot](../guides/snapshots.md):

- the library database, for changes to the library;
- the target files, for an export.

No write happens without a snapshot.

## 3. Apply

djlib then writes, with these checks:

1. **Nothing changed since the plan.** For an export, the hash of each target file must still match the one in the plan. For the library, its revision must be the same. If something changed, for instance because Mixxx saved its database in between, djlib stops with `stale_target` and writes nothing.
2. **Atomic writes.** Each file is written to a temporary name next to it and then renamed into place, so a file is never half written. Changes to the library run in one database transaction.
3. **Restore on failure.** If anything fails after writing started, djlib puts the snapshot back and reports `apply_failed`, saying whether the restore worked.

Running a command again after applying it plans nothing: there is nothing left to do.

## Why dry-run by default

Your library holds years of cues, playlists and tag work. A tool that writes first and lets you check afterwards is a tool you can only trust after it has hurt you. In djlib you see the whole change first, and a snapshot covers the case where you change your mind later.

The confirmation question is the last chance to stop. `--yes` skips it for scripts, which should look at the `--json` plan first. [Using djlib from another program](../guides/from-another-program.md) shows the flow.
