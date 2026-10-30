# Relocating tracks

When files are not where the library expects them, because a disk is mounted elsewhere, the library was made on another computer or a folder was renamed, `relocate` finds them again.

```sh
djlib list --missing                    # the tracks whose files are not here
djlib relocate /mnt/usb/Music           # show where they would point
djlib relocate /mnt/usb/Music --apply
```

## How files are found

djlib looks under the folder you name for files with the same name as each missing track's file. There is nothing to configure, and you do it once.

- When several files have the same name, the one under the same folders as before wins.
- If that does not settle it, the track is left alone and the plan says so.
- A file already used by another track is never taken.

## What changes

Only the path. Cues, playlists and tags stay, and later imports from the same beets or Mixxx library keep matching the track. Files on disk are not moved, renamed or read.

Walking a large or remote folder (sshfs, a NAS) can take a while. In a terminal, `relocate` shows the folder and how many files it has seen.

Imports can do the same on the fly with `--find-in`. See [importing from beets](import-beets.md#a-library-made-on-another-computer).
