# Snapshots and restore

Before any write, tunedex takes a **snapshot** of what it is about to change: the library database, the files of an export target, the tags of audio files, or file names. Any write can therefore be undone.

```sh
tunedex snapshot list
```

```text
TARGET              ID                       TIME                     REASON
library             000002-20261030T194448Z  2026-10-30 19:44:48 UTC  fix tags
library             000001-20261030T194441Z  2026-10-30 19:44:41 UTC  scan ~/Music
mixxx-2af9b1fc0f27  000001-20261030T194540Z  2026-10-30 19:45:40 UTC  export mixxx to ~/mixxx-test/mixxxdb.sqlite
```

## Targets

Snapshots are kept per **target**:

- `library` is tunedex's own library;
- `tags` holds the tags of the audio files [`write-tags`](write-tags.md) writes: every byte of each file outside its audio stream, never the audio;
- `renames` holds the old and new names of the files [`rename`](rename.md) renames, with the library;
- each export destination is a target named after its adapter and a short hash of its location, such as `mixxx-2af9b1fc0f27` or `m3u-568b52ce5ecb`.

A snapshot holds the state from just **before** the write named in `REASON`.

## Restoring

```sh
tunedex snapshot restore library 000002-20261030T194448Z           # show what it restores
tunedex snapshot restore library 000002-20261030T194448Z --apply
```

```text
Restore library to snapshot 000002-20261030T194448Z (fix tags):
  put back ~/.local/share/tunedex/library.db
Dry run: nothing was restored. Run again with --apply to restore it.
```

Files that did not exist when the snapshot was taken are removed, and the others are put back.

Two targets restore differently:

- **`tags`** rebuilds each audio file from its tags in the snapshot and the audio it has now, byte for byte as it was. It first checks that every file is there with the same audio; if one is missing or was re-encoded, nothing is restored.
- **`renames`** renames each file back, then puts the library back. It first checks that every renamed file is there and that no other file took an old name.

Before restoring, tunedex takes a new snapshot of the current state, so a restore can be undone too.

Close the DJ app before restoring its target, as you would before an export.

## Where they are kept

Snapshots live under `snapshots/` in the [tunedex home](../reference/environment.md#the-home-directory), one folder per target. Each one is a plain copy of the files with a small manifest, readable without tunedex. A `tags` snapshot holds, per file, the bytes before and after the audio one after the other; the manifest says where the audio was.
