# Importing from Mixxx

Bring your Mixxx library into djlib: tracks, keys, cues, loops, beat grids, playlists and crates.

```sh
djlib import mixxx                              # Mixxx's own library: show the plan
djlib import mixxx --apply
djlib import mixxx ~/mixxx-test --apply         # another profile, or a mixxxdb.sqlite file
```

Without a path, djlib reads the library of Mixxx's default profile.

## What is imported

- **Imported:** tracks with their tags, BPM and key, hot cues, the main cue, loops, beat grids, playlists and crates.
- **Not imported:** the Auto DJ queue and the history. The plan says how many were skipped.
- **Only read:** djlib reads a consistent copy of Mixxx's database, so the import works even while Mixxx is running. Nothing in Mixxx changes.

Playlists and crates go into a `Mixxx` folder in djlib, as `Mixxx/Playlists/...` and `Mixxx/Crates/...`. Each import replaces that folder; nothing else in djlib is touched.

## Importing again

Tracks are matched by path, and then by Mixxx's own track id.

- **The first import** only fills fields that are empty in djlib.
- **Later imports** take the changes made in Mixxx since the last one. If you also edited the same field in djlib, djlib keeps your value and the plan lists a **conflict**.

So you can keep using Mixxx and re-import whenever you like.

## Only part of the library

If some files are not on this computer yet, `--find-in` looks for them under a folder, the way [`relocate`](relocate.md) does, and imports only the tracks it finds:

```sh
djlib import mixxx --find-in ~/Music/Copied --apply
```

Run it again after copying more files. The tracks imported before are recognized.

## Trying it safely

Start Mixxx with a separate profile, so that your real library is never involved:

```sh
mixxx --settingsPath ~/mixxx-test
djlib import mixxx ~/mixxx-test
```

To send the library back to Mixxx, see [exporting to Mixxx](export-mixxx.md).
