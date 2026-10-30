# The library database

djlib keeps its library in one SQLite file, `library.db`, in the [home directory](../reference/environment.md#the-home-directory). It is your data in an open format: any SQLite tool can read it, and you do not need djlib to get your data out.

## The schema

The schema is defined in plain SQL files shipped with djlib, under [`src/djlib/store/schema/`](https://github.com/vonmartins/DJ-Open-Lib/tree/main/src/djlib/store/schema), with comments that explain each table and column. The main tables are:

| Table | Holds |
|---|---|
| `tracks` | One row per track: its id, paths and every tag. |
| `cues`, `beat_markers`, `tags`, `track_tags` | A track's cues and loops, beat grid and free tags. |
| `playlist_nodes`, `playlist_entries`, `smartlist_rules` | The playlist tree, the tracks in each playlist, in order, and smartlist rules. |
| `file_state` | What the last scan saw of each file: size, time, quick hash. |
| `sources`, `source_values` | Each import source, and the values it gave each track the last time. |
| `sync_state` | What was last exported to each target. |
| `merges`, `not_duplicates` | Merged tracks, and groups marked as not duplicates. |

The conventions are the same as in the [JSON formats](../reference/json.md): ids are UUID text, times are integer microseconds, and dates are ISO 8601 text.

You can read the database while djlib is not writing to it. Do not write to it yourself: djlib checks the library's revision before applying a plan, but it cannot check edits it does not know about.

## Identification and versions

- The file is marked as a djlib database (`PRAGMA application_id`, "DJLB"). djlib refuses to open any other SQLite file and leaves it untouched; that is the `not_a_library` error.
- The schema version is kept in `PRAGMA user_version`. A database written by a newer djlib is refused without changes (`library_too_new`).

## Upgrades

When a newer djlib opens an older library, it upgrades the schema:

1. It first writes a complete copy next to the original, named like `library.db.v6-20261030T120000Z.bak`. If the copy cannot be written, it stops.
2. It applies each pending migration in order, each in its own transaction.
3. If a migration fails, the database stays at the last version that succeeded, and the copy is still there.

## Atomic changes

Every write to the library either happens completely or not at all. A whole scan, import or fix plan is applied in one transaction, so an interrupted apply never leaves half a change behind.
