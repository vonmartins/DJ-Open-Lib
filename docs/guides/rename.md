# Renaming files

`rename` names each track's file after its tags, in its own folder: `sam_paganini-galaxy_www.slider.kz.mp3` becomes `Sam Paganini - Galaxy.mp3`.

```sh
tunedex fix --apply                                        # clean the tags first
tunedex rename --under ~/Music/dl                          # show the new names
tunedex rename --under ~/Music/dl --apply
tunedex rename --pattern "{artist} - {title}{ (remixer remix)}"
```

The plan shows each old and new name. Files stay in their folders and keep their extension.

## Patterns

The default pattern is `{artist} - {title}`. The pattern for a run comes from:

1. `--pattern`;
2. otherwise, the `rename` section of the [rules file](../reference/rules.md#rename), so that it can be versioned with the rest;
3. otherwise, the default.

In a pattern:

- `{field}` stands for a field: any text field, such as `artist`, `title`, `album`, `remixer` or `label`, and `year`, `bpm`, `key` and `track_number`.
    - `bpm` is a whole number.
    - `key` is in Open Key notation, such as `8m`.
    - `track_number` has two digits, such as `03`.
- `{ (remixer remix)}` is an **optional part**: text and one field inside the braces. It is written only when the field has a value, so `{artist} - {title}{ (remixer remix)}` gives `Bicep - Glue (Scuba remix).flac` and `Bicep - Glue.flac`.
- A field the pattern does not know is an error, and nothing is planned.

## Safe names

New names work on Linux, macOS and Windows:

- `/ \ * ? " < > |` and control characters become `_`, and `:` becomes ` -`. For example, `AC/DC - Who: Made Who?` becomes `AC_DC - Who - Made Who_.mp3`.
- Runs of spaces become one, and leading and trailing spaces and trailing dots go.
- Names Windows reserves, such as `CON` or `COM1`, get a trailing `_`.
- Names are cut to 255 bytes.

## Skips

Nothing is ever overwritten. These files keep their name, and a warning names them:

- a track that lacks a field the pattern needs outside an optional part, such as a track with no artist;
- a missing file;
- a name another file in the folder already has, ignoring case as macOS and Windows do;
- two tracks that would get the same name: both keep theirs.

A change of case only, such as `bicep - glue.mp3` to `Bicep - Glue.mp3`, goes through a temporary name, so it works on systems that ignore case.

## The library and other apps

The library follows the new names in the same apply. Tracks keep their id, tags, cues and playlists, and the next scan finds nothing new or missing.

Other apps still list the old names: a Mixxx database, M3U playlists you exported, or a beets library. The plan warns about each one tunedex knows the tracks are in. Export to them again after renaming. A Mixxx export matches tracks by path, so Mixxx then sees the renamed files as new tracks and keeps the old entries.

## Undo

The apply takes a snapshot of the target `renames`, which records each old and new name together with the library.

```sh
tunedex snapshot list renames
tunedex snapshot restore renames 000001-20261031T110000Z --apply
```

The restore renames each file back and puts the library back. It first checks that every renamed file is still there and that no other file has taken an old name. If one fails, nothing is restored and the files are named.

If a rename fails halfway, the files already renamed get their old names back and the library is left as it was.
