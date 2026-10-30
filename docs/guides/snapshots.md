# Snapshots and restore

Before any write, djlib takes a **snapshot** of what it is about to change: the library database, or the files of an export target. Any write can therefore be undone.

```sh
djlib snapshot list
```

```text
TARGET              ID                       TIME                     REASON
library             000002-20261030T194448Z  2026-10-30 19:44:48 UTC  fix tags
library             000001-20261030T194441Z  2026-10-30 19:44:41 UTC  scan ~/Music
mixxx-2af9b1fc0f27  000001-20261030T194540Z  2026-10-30 19:45:40 UTC  export mixxx to ~/mixxx-test/mixxxdb.sqlite
```

## Targets

Snapshots are kept per **target**:

- `library` is djlib's own library;
- each export destination is a target named after its adapter and a short hash of its location, such as `mixxx-2af9b1fc0f27` or `m3u-568b52ce5ecb`.

A snapshot holds the state from just **before** the write named in `REASON`.

## Restoring

```sh
djlib snapshot restore library 000002-20261030T194448Z           # show what it restores
djlib snapshot restore library 000002-20261030T194448Z --apply
```

```text
Restore library to snapshot 000002-20261030T194448Z (fix tags):
  put back ~/.local/share/djlib/library.db
Dry run: nothing was restored. Run again with --apply to restore it.
```

Files that did not exist when the snapshot was taken are removed, and the others are put back.

Before restoring, djlib takes a new snapshot of the current state, so a restore can be undone too.

Close the DJ app before restoring its target, as you would before an export.

## Where they are kept

Snapshots live under `snapshots/` in the [djlib home](../reference/environment.md#the-home-directory), one folder per target. Each one is a plain copy of the files with a small manifest, readable without djlib.
