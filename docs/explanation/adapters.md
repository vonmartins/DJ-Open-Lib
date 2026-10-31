# Adapters and losses

An **adapter** connects tunedex to a format or an app: it reads it, and for targets it plans what to write. Each adapter declares what its format can hold, its **capabilities**. Whatever the library has that the format cannot hold is a **loss**.

tunedex never hides a loss. The plan lists each one with how many tracks it affects and a few examples, before anything is written:

```text
Losses: 2
  - remixer is not stored: 8 (e.g. DFRNT - Headspace (Scuba Remix), …)
  - date_modified is not stored: 44 (e.g. Alley Cat - Mary in the Mirror, …)
```

A loss only concerns the target. The library keeps everything.

## Adapters today

| | Mixxx | M3U |
|---|---|---|
| Reads | yes ([import](../guides/import-mixxx.md)) | no |
| Writes | yes ([export](../guides/export-mixxx.md)) | yes ([export](../guides/export-m3u.md)) |
| Track fields | artist, title, album, album artist, genre, composer, grouping, comment, year, track number, length, bitrate, sample rate, file format, BPM, key, rating, color, play count, last played, date added | artist, title, length |
| Hot cues, memory cues, loops | yes | no |
| Beat grids | yes | no |
| Tags | no | no |
| Folders | flattened into names: `Techno / Peak` | yes, as subfolders |
| Smartlists | no | no |
| Tracks in no playlist | yes | no |

For tracks Mixxx already has, an export updates the text fields, year, track number, rating, color, BPM and key. The other fields are only written for tracks it adds, because Mixxx itself keeps them up to date.

## Unmapped data

Formats hold things tunedex has no field for. They are kept with the track or playlist as **unmapped** data, under the name of the format they came from, and written back when tunedex writes to that format again. Nothing is thrown away just because tunedex does not understand it.

## Sources

The folder scan and beets are **sources**: they are only read and never written. The beets source keeps every beets tag that has no tunedex field as unmapped data under `beets`.

## Adapters are never the app

Adapters read and write files. They never need the app installed and never talk to it while it runs. This is why Mixxx has to be closed for an export: tunedex checks for it and refuses otherwise. It also explains the `stale_target` check described in [plan, snapshot, apply](plan-apply.md).
