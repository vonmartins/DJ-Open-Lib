# Exporting to Mixxx

Write djlib's library to Mixxx: tracks, tags, cues, loops, beat grids, playlists and crates.

**Quit Mixxx first.** djlib refuses to write while Mixxx runs.

```sh
djlib export mixxx                               # Mixxx's own library: show the plan
djlib export mixxx --apply
djlib export mixxx ~/mixxx-test --apply          # another profile
djlib export mixxx --playlist Techno/Peak        # only some playlists
djlib export mixxx --modified --apply            # only playlists changed since the last export
```

## What is written

- **Written:** track metadata, BPM and key, hot cues, the main cue, loops, beat grids, tracks Mixxx does not have yet, playlists and crates.
- **Kept as it is:** everything else in Mixxx's database, such as analysis data, cover art, ReplayGain, Auto DJ and history.
- **Never deleted:** nothing is removed from Mixxx, and tracks you removed from Mixxx are not brought back.
- **Not stored:** smartlists, tags and memory cues beyond the main cue cannot be stored in Mixxx. The plan lists them as [losses](../explanation/adapters.md).

## Playlists

- Playlists from the `Mixxx` folder, the ones [imported from Mixxx](import-mixxx.md), go back to the playlist or crate they came from.
- Other playlists become Mixxx playlists named after their path: `Techno/Peak` is written as `Techno / Peak`. They are not imported back as copies.

## Conflicts

A field edited in Mixxx since the last import is left as Mixxx has it, and the plan shows a conflict. Import first to bring the Mixxx value into djlib.

## Undoing an export

The previous database is kept as a snapshot. With Mixxx closed, `djlib snapshot restore` puts it back; see [snapshots and restore](snapshots.md).
