# Exporting to M3U

Write the library's playlists as `.m3u8` files, which almost every player and DJ app can open.

```sh
tunedex export m3u ~/Playlists                          # show the plan
tunedex export m3u ~/Playlists --apply
tunedex export m3u ~/Playlists --playlist Techno/Peak   # only some playlists
tunedex export m3u ~/Playlists --modified --apply       # only playlists changed since the last export
tunedex export m3u ~/Playlists --relative-paths --apply
```

## What is written

- One `.m3u8` file per playlist, in UTF-8, with each track's artist, title and length.
- Folders become subfolders: `Sets/Friday` is written as `Sets/Friday.m3u8`.
- Track paths are absolute. With `--relative-paths` they are relative to each playlist file, which suits a USB stick that is mounted in different places.

M3U holds only paths and playlist order. BPM, key, cues and the other tags are not written, and neither are smartlists or tracks in no playlist. The plan lists these as [losses](../explanation/adapters.md).

## Exporting again

- Exports never delete anything. Playlists that exist only in the folder are left alone and reported.
- `--modified` writes only the playlists changed since the last export to the same folder.
- There is no full sync (mirroring) mode.

Each apply takes a [snapshot](snapshots.md) of the files it overwrites first.
