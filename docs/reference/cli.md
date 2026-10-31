# Commands

Free, local-first, scriptable DJ library manager.

**Usage**:

```console
$ tunedex [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--home <path>`: Directory for the library and the snapshots. Default: $TUNEDEX_HOME, else the user data directory.
* `--no-color`: Print without color. Also: NO_COLOR=1.
* `--version`: Show the version and exit.
* `--help`: Show this message and exit.

Commands that change something show a plan and write nothing unless --apply is given. --json prints one JSON document instead. Exit codes: 0 success (also a dry run or a declined plan), 1 error, 2 wrong usage.

**Commands**:

* `status`: Show a summary of the library: tracks,...
* `list`: List the library's tracks, one per line,...
* `show`: Show everything tunedex knows about one...
* `playlists`: Show the playlist tree, with the number of...
* `scan`: Add, update, move and mark missing the...
* `relocate`: Find, under a folder, the files of the...
* `fix`: Clean the tags of the library's tracks...
* `enrich`: Fill in tags from MusicBrainz for the...
* `dupes`: Report tracks that are the same song, and...
* `write-tags`: Write the library's tags into the audio...
* `rename`: Rename the tracks' files from their tags,...
* `import`: Import tracks and playlists from another app.
* `export`: Export the library to another format or app.
* `snapshot`: List and restore snapshots.

## `tunedex status`

Show a summary of the library: tracks, playlists, sources, snapshots, duplicates.

Example: tunedex status

**Usage**:

```console
$ tunedex status [OPTIONS]
```

**Options**:

* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex list`

List the library's tracks, one per line, by artist and title.

Example: tunedex list --where "genre=Techno" --where "bpm>130"

**Usage**:

```console
$ tunedex list [OPTIONS]
```

**Options**:

* `-w, --where <str>`: Only tracks where FIELD OP VALUE holds, such as bpm>=170 or title~remix. Operators: = != ~ !~ > >= < <=. Repeatable; all must hold.
* `--under <path>`: Only the tracks under this folder.
* `-p, --playlist <str>`: Playlist or folder path such as Techno/Peak; repeatable.
* `--missing`: Only tracks whose file is not on this computer.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex show`

Show everything tunedex knows about one track.

Its tags, cues, loops, beat grid, playlists and the apps it was imported from.

Example: tunedex show ~/Music/techno/a.flac

**Usage**:

```console
$ tunedex show [OPTIONS] {TRACK}
```

**Arguments**:

* `TRACK`: Path of the track's file, or its id.  [required]

**Options**:

* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex playlists`

Show the playlist tree, with the number of tracks of each playlist.

Example: tunedex playlists

**Usage**:

```console
$ tunedex playlists [OPTIONS]
```

**Options**:

* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex scan`

Add, update, move and mark missing the tracks of a music folder.

Tags are read from the files; the files are never changed.

Example: tunedex scan ~/Music --apply

**Usage**:

```console
$ tunedex scan [OPTIONS] {folder}
```

**Arguments**:

* `folder`: Music folder to scan.  [required]

**Options**:

* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex relocate`

Find, under a folder, the files of the tracks that are missing on this computer.

Files are found by name; nothing on disk is moved, renamed or read.

Example: tunedex relocate /mnt/usb/Music --apply

**Usage**:

```console
$ tunedex relocate [OPTIONS] {folder}
```

**Arguments**:

* `folder`: Folder where the files are now.  [required]

**Options**:

* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex fix`

Clean the tags of the library's tracks with the bundled fixes and your rules.

Fixes remove URLs, video ids and odd characters, and move featured artists and
remixers to their fields. Each change names the fix or rule that made it. Only the
library changes; audio files are never touched.

Example: tunedex fix --only remove_urls --under ~/Music/new

**Usage**:

```console
$ tunedex fix [OPTIONS]
```

**Options**:

* `--rules <path>`: Rules file. Default: rules.yaml in the tunedex home if it exists, else the bundled fixes.
* `--only <str>`: Only this fix or rule id; repeatable, or separated by commas.
* `--under <path>`: Only the tracks under this folder.
* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex enrich`

Fill in tags from MusicBrainz for the tracks AcoustID recognizes by their sound.

Sends each file's fingerprint (from fpcalc) to AcoustID, then asks MusicBrainz. The
only command that uses the network; answers are cached in the tunedex home. Edits made
in tunedex are kept, and audio files are never touched.

Example: tunedex enrich --under ~/Music/new

**Usage**:

```console
$ tunedex enrich [OPTIONS]
```

**Options**:

* `--under <path>`: Only the tracks under this folder.
* `--refresh`: Ask AcoustID and MusicBrainz again, ignoring the cache.
* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex dupes`

Report tracks that are the same song, and suggest which one to keep.

With --merge --apply, asks about each group, then shows one plan: the kept track takes
the others' tags, cues, playlists and plays, and their files go to the system trash.
--keep, --skip and --ignore answer for a group without asking.

Example: tunedex dupes --merge --keep ~/Music/a.flac --apply

**Usage**:

```console
$ tunedex dupes [OPTIONS]
```

**Options**:

* `--merge`: Plan merging each group into one track.
* `--keep <path>`: Keep this track in its group (repeatable).
* `--skip <path>`: Leave the group of this track unmerged (repeatable).
* `--ignore <path>`: Mark the group of this track as not duplicates (repeatable).
* `--keep-files`: Merge in the library only; move no file to the trash.
* `--under <path>`: Only the groups with a track under this folder.
* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex write-tags`

Write the library's tags into the audio files, so other apps and players see them.

Only fields that differ are written: title, artist, album, album artist, genre, year,
track and disc number, BPM, key, composer, remixer, label, comment, grouping and
lyricist. Cover art and every other tag stay. MP3, FLAC, WAV and AIFF files are
written; files changed since the last scan are skipped. A snapshot of the tags
(target tags) is taken first, so the write can be undone.

Example: tunedex write-tags --under ~/Music/new --apply

**Usage**:

```console
$ tunedex write-tags [OPTIONS]
```

**Options**:

* `--under <path>`: Only the tracks under this folder.
* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex rename`

Rename the tracks' files from their tags, each in its own folder.

Placeholders are any text field, {year}, {bpm}, {key} and {track_number}; a part in
braces with text and one field, such as { (remixer remix)}, is left out when the
field is empty. Names are made safe on every system. Tracks missing a field, and
names already taken, are skipped: no file is ever overwritten. The library follows
the new names; other apps that list the files keep the old ones.

Example: tunedex rename --under ~/Music/dl --pattern "{artist} - {title}"

**Usage**:

```console
$ tunedex rename [OPTIONS]
```

**Options**:

* `--pattern <str>`: File name pattern, such as '{artist} - {title}{ (remixer remix)}'. Default: the rename pattern of rules.yaml in the tunedex home, else '{artist} - {title}'.
* `--under <path>`: Only the tracks under this folder.
* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex import`

Import tracks and playlists from another app.

**Usage**:

```console
$ tunedex import [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `mixxx`: Import a Mixxx library: tracks, cues,...
* `beets`: Import the tracks of a beets library and...

### `tunedex import mixxx`

Import a Mixxx library: tracks, cues, loops, grids, playlists and crates.

Mixxx's files are only read. Its playlists and crates go to a "Mixxx" folder in
tunedex, which later imports replace.

Example: tunedex import mixxx --apply

**Usage**:

```console
$ tunedex import mixxx [OPTIONS] [database]
```

**Arguments**:

* `database`: mixxxdb.sqlite or the Mixxx settings directory. Default: Mixxx's own.

**Options**:

* `--find-in <path>`: Look for tracks whose files are not on this computer in this folder; only the ones found are imported.
* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

### `tunedex import beets`

Import the tracks of a beets library and their tags.

beets' database and the music files are only read. Albums do not become playlists.

Example: tunedex import beets ~/Music/.beets.db --apply

**Usage**:

```console
$ tunedex import beets [OPTIONS] [library]
```

**Arguments**:

* `library`: beets' library.db (or its directory). Default: beets' own.

**Options**:

* `--music-dir <path>`: beets' music directory, for libraries with relative paths. Default: `directory` in beets' config.yaml, or ~/Music.
* `--find-in <path>`: Look for tracks whose files are not on this computer in this folder; only the ones found are imported.
* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex export`

Export the library to another format or app.

**Usage**:

```console
$ tunedex export [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `m3u`: Write the library's playlists as M3U8...
* `mixxx`: Write the library to a Mixxx library.

### `tunedex export m3u`

Write the library's playlists as M3U8 files under a folder.

Folders become subfolders. The folder is created when the plan is applied.

Example: tunedex export m3u ~/Playlists -p Techno --apply

**Usage**:

```console
$ tunedex export m3u [OPTIONS] {FOLDER}
```

**Arguments**:

* `FOLDER`: Folder for the .m3u8 files.  [required]

**Options**:

* `-p, --playlist <str>`: Playlist or folder path such as Techno/Peak; repeatable.
* `--modified`: Only playlists changed since the last export there.
* `--relative-paths`: Write track paths relative to each playlist file.
* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

### `tunedex export mixxx`

Write the library to a Mixxx library. Quit Mixxx first.

Tracks, cues, loops, grids, playlists and crates are written. Fields edited in Mixxx
since the last import are left as they are and shown as conflicts. Nothing in Mixxx
is deleted.

Example: tunedex export mixxx --modified --apply

**Usage**:

```console
$ tunedex export mixxx [OPTIONS] [database]
```

**Arguments**:

* `database`: mixxxdb.sqlite or the Mixxx settings directory. Default: Mixxx's own.

**Options**:

* `-p, --playlist <str>`: Playlist or folder path such as Techno/Peak; repeatable.
* `--modified`: Only playlists changed since the last export there.
* `--apply`: Apply the plan (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

## `tunedex snapshot`

List and restore snapshots.

**Usage**:

```console
$ tunedex snapshot [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List snapshots, newest first, with their...
* `restore`: Put the files of a target back as they...

### `tunedex snapshot list`

List snapshots, newest first, with their target, id, time and reason.

Example: tunedex snapshot list library

**Usage**:

```console
$ tunedex snapshot list [OPTIONS] [target]
```

**Arguments**:

* `target`: Only this target, such as library.

**Options**:

* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.

### `tunedex snapshot restore`

Put the files of a target back as they were in a snapshot.

Shows the files it would put back, remove or rename back; --apply restores them.
The current state is saved in a new snapshot first, so a restore can be undone.

Example: tunedex snapshot restore library 000012-20261029T120000Z --apply

**Usage**:

```console
$ tunedex snapshot restore [OPTIONS] {target} {ID}
```

**Arguments**:

* `target`: Target name, as shown by tunedex snapshot list.  [required]
* `ID`: Snapshot identifier.  [required]

**Options**:

* `--apply`: Restore the snapshot (asks for confirmation).
* `-y, --yes`: Do not ask for confirmation.
* `--json`: Print only a JSON document on stdout.
* `--help`: Show this message and exit.
