# Merging duplicates

Find tracks that are the same song and keep the best copy of each.

```sh
djlib dupes                      # report the groups
djlib dupes --merge              # show the merge plan
djlib dupes --merge --apply      # decide group by group
```

`djlib dupes` lists groups of tracks that are the same song. For each file it shows the format, bitrate, length, cues and playlists, and marks the one it suggests keeping.

## Same song

Two tracks are the same song when:

- they have the same MusicBrainz recording, from [`enrich`](enrich.md) or beets; or
- they have the same artist and title, with lengths within 3 seconds. Case, `(Original Mix)`, video ids, URLs and where a `feat.` guest is written are ignored.

Remixes, VIPs, edits and extended mixes are different songs and are never grouped.

## The suggested track

The first criterion that tells two tracks apart decides:

1. a file that is present on this computer;
2. lossless before lossy;
3. the higher bitrate;
4. more cues;
5. a beat grid;
6. more playlists;
7. the oldest in the library.

## Merging

With `--merge --apply` in a terminal, djlib shows each group and you answer:

| Answer | Effect |
|---|---|
| Enter | Keep the marked track. |
| a number | Keep that track. |
| `s` | Skip this group for now. |
| `i` | Not duplicates: never show this group again. |
| `q` | Stop asking. |

Then one plan shows everything and asks once.

From a script, give the answers as options: `--keep PATH` chooses the track to keep, `--skip PATH` and `--ignore PATH` act on a track's group, and `--yes` takes the suggestions for the rest:

```sh
djlib dupes --merge --keep ~/Music/a.flac --skip ~/Music/b.mp3 --apply --yes
```

## What the kept track gets

- the others' values for its empty fields;
- their cues and beat grid, if it has none;
- their playlist entries;
- the sum of the play counts, the highest rating, the oldest date added and all the tags.

## The other files

They go to the **system trash**, so they can be recovered; djlib never deletes a file for good.

- A file that cannot be trashed (some network mounts have no trash) is left in place and reported.
- `--keep-files` merges in djlib only and leaves every file where it is.
- The plan warns when a file belongs to your beets or Mixxx library, which will then miss it. Later imports from them update the kept track instead of bringing the merged one back.
