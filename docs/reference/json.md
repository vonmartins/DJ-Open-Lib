# JSON formats

With `--json`, a command prints exactly one JSON document on standard output and nothing else. Questions and progress go to standard error. An error is a [JSON error document](errors.md) on standard error.

Every document starts with `format`, which names it, and `version`. A new version means an incompatible change, such as a field removed, renamed or given another meaning. New fields can appear without a new version, so a client should ignore the fields it does not know.

| Format | Version | Printed by |
|---|---|---|
| [`tunedex-plan`](#tunedex-plan) | 3 | `scan`, `relocate`, `fix`, `enrich`, `dupes --merge`, `import mixxx`, `import beets`, `export m3u`, `export mixxx` |
| [`tunedex-status`](#tunedex-status) | 1 | `status` |
| [`tunedex-tracks`](#tunedex-tracks) | 1 | `list` |
| [`tunedex-track`](#tunedex-track) | 1 | `show` |
| [`tunedex-playlists`](#tunedex-playlists) | 1 | `playlists` |
| [`tunedex-dupes`](#tunedex-dupes) | 1 | `dupes` |
| [`tunedex-snapshots`](#tunedex-snapshots) | 1 | `snapshot list` |
| [`tunedex-restore`](#tunedex-restore) | 1 | `snapshot restore` |

Conventions in every format:

- **Times** are integer microseconds (`duration_us`, `start_us`).
- **Dates** are ISO 8601 text: `2026-10-30`, and `2026-10-30T19:39:27+00:00` with a time.
- **Paths** are absolute paths on this computer, as text.
- **Unknown values** are `null`; a field is never left out.

## `tunedex-plan`

**Version 3.** Every command that changes something prints its plan. Without `--apply` this is a dry run and `result` is `null`. With `--apply`, the same document also carries the result.

```json
{
  "format": "tunedex-plan",
  "version": 3,
  "target": "m3u-568b52ce5ecb",
  "title": "export m3u to /home/ana/playlists",
  "location": "/home/ana/playlists",
  "empty": false,
  "tracks": [],
  "refreshed": 0,
  "rebased": 0,
  "playlists": [
    {
      "change": "added",
      "path": ["Sets", "Friday"],
      "kind": "playlist",
      "entries_added": ["/home/ana/Music/techno/a.mp3", "/home/ana/Music/techno/b.mp3"],
      "entries_removed": [],
      "reordered": false,
      "renamed_from": null
    }
  ],
  "untouched_playlists": 0,
  "files": [
    {
      "path": "/home/ana/playlists/Sets/Friday.m3u8",
      "action": "create",
      "bytes": 292,
      "sha256_before": null,
      "sha256_after": "834823acbe34b22a240548e1e51a87b08fb431e2a4cd44d6ed9930c5e2a9808e",
      "description": "create playlist 'Friday' (2 entries)"
    }
  ],
  "trash": [],
  "losses": [
    {
      "kind": "field:bpm",
      "description": "bpm is not stored",
      "count": 2,
      "examples": ["Velk - Rise", "Arno - Fall"]
    }
  ],
  "warnings": [],
  "conflicts": [],
  "result": {
    "status": "applied",
    "snapshot": "000001-20261030T193927Z",
    "files_written": 1,
    "operations_applied": 0,
    "files_trashed": 0,
    "warnings": []
  }
}
```

| Field | Type | Meaning |
|---|---|---|
| `target` | string | What the plan changes: `library` for the tunedex library, or `<adapter>-<12 hex digits>` for an export target. Snapshots are kept per target. |
| `title` | string | A one-line description of the plan. |
| `location` | string or null | The folder or file the plan writes to; `null` for the library. |
| `empty` | boolean | `true` when there is nothing to do. |
| `tracks` | array of [track changes](#track-change) | Tracks added, updated, moved, missing, present again or merged. |
| `refreshed` | integer | Files whose recorded state was refreshed without any field change (scans only). |
| `rebased` | integer | Tracks whose import base was updated without any field change (imports only). |
| `playlists` | array of [playlist changes](#playlist-change) | Folders, playlists and smartlists added, updated or removed. |
| `untouched_playlists` | integer | Playlists in the target that the library does not have. They are left alone (exports only). |
| `files` | array of [file changes](#file-change) | Every file the apply would write (exports only). |
| `trash` | array | Audio files the apply would move to the system trash (`dupes --merge`): `path` and `bytes`. |
| `losses` | array of [losses](#loss) | What the target cannot keep. |
| `warnings` | array of strings | Things to know before applying. |
| `conflicts` | array of [conflicts](#conflict) | Fields edited in tunedex whose tag also changed in the file (scans). tunedex's value is kept. |
| `result` | [result](#result) or null | What the apply did; `null` in a dry run. |

### Track change

| Field | Type | Meaning |
|---|---|---|
| `change` | string | `added`, `updated`, `moved`, `missing`, `present` or `merged`. |
| `track_id` | string or null | The track's id; `null` for a track the plan adds. |
| `path` | string | The track's path, after the change. |
| `old_path` | string or null | For a moved track, the path before. |
| `merged_into` | string or null | For a merged track, the path of the track it was merged into. |
| `name` | string | How the track is shown: `artist - title`, or the file name. |
| `fields` | array | Each changed field: `field`, `before`, `after`, and `by`, the fix, rule or source that made the change (or `null`). For an added track, every field it has, from `null`. |

### Playlist change

| Field | Type | Meaning |
|---|---|---|
| `change` | string | `added`, `updated` or `removed`. |
| `path` | array of strings | The names from the top folder down to this node. |
| `kind` | string | `folder`, `playlist` or `smartlist`. |
| `entries_added`, `entries_removed` | arrays of strings | Paths of the tracks added to or removed from the playlist. |
| `reordered` | boolean | Whether the order of the entries changed. |
| `renamed_from` | array of strings or null | The previous path of a renamed node. |

### File change

| Field | Type | Meaning |
|---|---|---|
| `path` | string | The file to write. |
| `action` | string | `create` or `update`. |
| `bytes` | integer | The size of the new content. |
| `sha256_before` | string or null | The hash of the file when the plan was made; `null` for a new file. The apply stops with `stale_target` if it no longer matches. |
| `sha256_after` | string | The hash of the new content. |
| `description` | string | What the change is, in words. |

### Loss

| Field | Type | Meaning |
|---|---|---|
| `kind` | string | What is lost, such as `field:bpm` or `tracks-outside-playlists`. |
| `description` | string | The loss in words. |
| `count` | integer | How many tracks or items it affects. |
| `examples` | array of strings | A few of them, by name. |

### Conflict

| Field | Type | Meaning |
|---|---|---|
| `track_id`, `path`, `name` | strings | The track. |
| `field` | string | The field. |
| `library_value` | any | The value in tunedex, which is kept. |
| `file_value` | any | The value now in the file's tags. |

### Result

| Field | Type | Meaning |
|---|---|---|
| `status` | string | `applied`; `declined` when the confirmation was refused; `nothing` when the plan was empty. |
| `snapshot` | string or null | The snapshot taken before writing. |
| `files_written` | integer | Files written to the target. |
| `operations_applied` | integer | Changes written to the library. |
| `files_trashed` | integer | Audio files moved to the system trash. |
| `warnings` | array of strings | Problems that did not stop the apply, such as a file that could not be trashed. |

## `tunedex-status`

**Version 1.** A summary of the library.

```json
{
  "format": "tunedex-status",
  "version": 1,
  "home": "/home/ana/.local/share/tunedex",
  "library_exists": true,
  "tracks": 4,
  "missing": 0,
  "playlists": 2,
  "smartlists": 0,
  "folders": 1,
  "sources": [{"name": "mixxx", "imported_at": "2026-10-30T19:20:02+00:00"}],
  "snapshots": [
    {
      "target": "library",
      "id": "000003-20261030T193927Z",
      "created_at": "2026-10-30T19:39:27+00:00",
      "reason": "scan /home/ana/Music"
    }
  ],
  "duplicate_groups": 1
}
```

| Field | Type | Meaning |
|---|---|---|
| `home` | string | The home directory in use. |
| `library_exists` | boolean | `false` when nothing was applied to this home yet. The counts are then 0. |
| `tracks`, `missing` | integers | Tracks in the library, and how many of their files are not on this computer. |
| `playlists`, `smartlists`, `folders` | integers | Nodes in the playlist tree. |
| `sources` | array | Each source imported from, with `name` and `imported_at`. |
| `snapshots` | array | The newest snapshot of each target: `target`, `id`, `created_at`, `reason`. |
| `duplicate_groups` | integer | Groups that `tunedex dupes` would report. |

## `tunedex-tracks`

**Version 1.** The tracks that match the filters, by artist and title.

```json
{
  "format": "tunedex-tracks",
  "version": 1,
  "tracks": [
    {
      "path_origin": "/home/ana/Music/techno/a.mp3",
      "id": "50a8cc13-633d-4e86-b983-5d263d6c0c09",
      "path": "/home/ana/Music/techno/a.mp3",
      "title": "Rise",
      "artist": "Velk",
      "genre": "Techno",
      "bpm": 132.0,
      "key": {"open_key": "8m", "musical": "Bbm"},
      "duration_us": 386856000,
      "bitrate": 320,
      "file_format": "mp3",
      "tags": [],
      "cues": [],
      "beatgrid": null,
      "unmapped": {}
    }
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `tracks` | array of [tracks](#track) | The matching tracks. |

The example is shortened: every [track](#track) field is always present.

### Track

| Field | Type | Meaning |
|---|---|---|
| `id` | string | A stable UUID, assigned on first import. It never changes, even when the file moves. |
| `path` | string | The normalized path, used to recognize the same file across imports. |
| `path_origin` | string | The path exactly as the source gave it. |
| `title`, `artist`, `album`, `album_artist`, `original_artist`, `genre`, `composer`, `producer`, `lyricist`, `remixer`, `mix`, `label`, `grouping`, `comment`, `extra1`, `extra2` | string or null | Text tags. |
| `year`, `track_number`, `disc_number` | integer or null | |
| `bpm` | number or null | Beats per minute, as stored. |
| `key` | object or null | The musical key in both notations: `open_key` (`1m`–`12m`, `1d`–`12d`) and `musical` (`Am`, `C`, ...). |
| `key_original` | string or null | The key as the source wrote it. |
| `rating` | integer or null | 0 to 5. |
| `color` | string or null | `#rrggbb`. |
| `play_count` | integer or null | |
| `date_added`, `date_modified`, `release_date` | string or null | Dates. |
| `last_played` | string or null | Date and time. |
| `duration_us` | integer or null | Length in microseconds. |
| `bitrate`, `sample_rate` | integer or null | In kbit/s and Hz. |
| `file_format` | string or null | `mp3`, `flac`, `wav`, `aiff`, `m4a`, ... |
| `energy`, `danceability`, `happiness`, `popularity` | integer or null | 0 to 10. |
| `tags` | array of strings | Free tags. |
| `cues` | array | Cues and loops: `kind` (`hot`, `memory` or `loop`), `start_us`, `slot` (the hot-cue pad, or `null`), `name`, `color`, `end_us` (loops only), `active`, `unmapped`. |
| `beatgrid` | object or null | `markers`: each with `position_us`, `bpm`, and `beat`, its place in the bar (1–4). Several markers mean tempo changes. |
| `unmapped` | object | Fields a source has that tunedex does not model. They are kept so they can be written back. |

## `tunedex-track`

**Version 1.** One track, with where it is used.

```json
{
  "format": "tunedex-track",
  "version": 1,
  "track": {"id": "50a8cc13-633d-4e86-b983-5d263d6c0c09", "path": "/home/ana/Music/techno/a.mp3"},
  "present": true,
  "playlists": ["Sets/Friday"],
  "sources": ["mixxx"]
}
```

| Field | Type | Meaning |
|---|---|---|
| `track` | [track](#track) | Every field of the track (shortened in the example). |
| `present` | boolean | Whether the file is on this computer. |
| `playlists` | array of strings | Paths of the playlists and smartlists that hold the track, in tree order. |
| `sources` | array of strings | The sources it was imported from, sorted. |

## `tunedex-playlists`

**Version 1.** The playlist tree, depth first.

```json
{
  "format": "tunedex-playlists",
  "version": 1,
  "nodes": [
    {"name": "Sets", "kind": "folder", "depth": 0, "tracks": null, "path": "Sets"},
    {"name": "Friday", "kind": "playlist", "depth": 1, "tracks": 2, "path": "Sets/Friday"},
    {"name": "Saturday", "kind": "playlist", "depth": 1, "tracks": 1, "path": "Sets/Saturday"}
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `nodes` | array | Each folder, playlist and smartlist, in tree order. |
| `nodes[].kind` | string | `folder`, `playlist` or `smartlist`. |
| `nodes[].depth` | integer | 0 for the top level. |
| `nodes[].tracks` | integer or null | Tracks in a playlist or selected by a smartlist; `null` for folders. |
| `nodes[].path` | string | The path that `--playlist` takes, such as `Sets/Friday`. |

## `tunedex-dupes`

**Version 1.** Groups of tracks that are the same song. The suggested track to keep comes first.

```json
{
  "format": "tunedex-dupes",
  "version": 1,
  "groups": [
    {
      "name": "Arno - Glow",
      "reason": "playlists",
      "tracks": [
        {
          "track_id": "2bbb4707-8d7d-4e1a-8200-7ebfa80f7371",
          "path": "/home/ana/Music/house/c.mp3",
          "format": "mp3",
          "bitrate": 320,
          "duration_us": 301000000,
          "cues": 0,
          "playlists": 1,
          "present": true,
          "suggested": true
        },
        {
          "track_id": "3cade962-60b1-4d52-afde-a4b5f88881e9",
          "path": "/home/ana/Music/house/c copy.mp3",
          "format": "mp3",
          "bitrate": 320,
          "duration_us": 301000000,
          "cues": 0,
          "playlists": 0,
          "present": true,
          "suggested": false
        }
      ]
    }
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `groups[].name` | string | The song, as `artist - title`. |
| `groups[].reason` | string | Why the first track is suggested over the second: `file present`, `lossless`, `bitrate`, `cues`, `beat grid`, `playlists`, `oldest` or `path`. |
| `groups[].tracks` | array | The tracks, best first. Each has `track_id`, `path`, `format`, `bitrate`, `duration_us`, `cues` (a count), `playlists` (a count), `present` and `suggested`. |

## `tunedex-snapshots`

**Version 1.** The snapshots of every target, newest first within each target.

```json
{
  "format": "tunedex-snapshots",
  "version": 1,
  "snapshots": [
    {
      "target": "m3u-568b52ce5ecb",
      "id": "000001-20261030T193927Z",
      "created_at": "2026-10-30T19:39:27.271558+00:00",
      "reason": "export m3u to /home/ana/playlists",
      "tunedex_version": "0.1.0",
      "files": ["/home/ana/playlists/Sets/Friday.m3u8", "/home/ana/playlists/Sets/Saturday.m3u8"]
    }
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `snapshots[].target` | string | The target the snapshot belongs to, as in a plan. |
| `snapshots[].id` | string | The id that `snapshot restore` takes. |
| `snapshots[].created_at` | string | When it was taken. |
| `snapshots[].reason` | string | The plan it was taken before. |
| `snapshots[].tunedex_version` | string | The tunedex version that took it. |
| `snapshots[].files` | array of strings | The files it holds. |

## `tunedex-restore`

**Version 1.** What restoring a snapshot does. Without `--apply`, `result` is left out.

```json
{
  "format": "tunedex-restore",
  "version": 1,
  "target": "m3u-568b52ce5ecb",
  "snapshot": "000001-20261030T193927Z",
  "files": [
    {"path": "/home/ana/playlists/Sets/Friday.m3u8", "action": "put_back"},
    {"path": "/home/ana/playlists/Sets/New.m3u8", "action": "remove"}
  ],
  "result": {"status": "restored", "pre_restore": "000002-20261030T194502Z"}
}
```

| Field | Type | Meaning |
|---|---|---|
| `target`, `snapshot` | strings | What is restored. |
| `files[].action` | string | `put_back`: the file returns to its content in the snapshot. `remove`: the file did not exist then and is deleted. |
| `result` | object | Only with `--apply`. `status` is `restored` or `declined`. On `restored`, `pre_restore` is the snapshot taken just before, so the restore can itself be undone. |
