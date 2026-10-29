# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Merging duplicates (`djlib dupes`): tracks that are the same song (same MusicBrainz
  recording, or same normalized artist and title with lengths within 3 seconds; versions
  stay apart) are reported with their format, bitrate, cues and playlists and a
  suggested track to keep. `--merge` asks group by group, then plans one merge: the kept
  track inherits empty fields, cues, playlist entries, plays and tags, and the other
  files go to the system trash (`--keep-files` to keep them). Merges and groups marked
  as not duplicates are remembered (schema version 7), so imports and scans do not bring
  them back. Plans can now move audio files to the trash; the plan JSON is version 3,
  with the `merged` track change, `merged_into` and `trash`.
- Enriching tags (`djlib enrich`): tracks are fingerprinted with `fpcalc`, recognized
  by AcoustID and tagged from MusicBrainz (title, artist, remixer, album, dates, label,
  track and disc numbers; the genre only when empty), through a plan where each change
  is marked `musicbrainz`. The first run normalizes; later runs keep edits made in
  djlib. Ambiguous, unknown and disagreeing tracks are reported, never guessed.
  Answers are cached in the djlib home (`--refresh` asks again), `--under FOLDER`
  limits the run, and no other command uses the network.
- Cleaning tags (`djlib fix`): ten bundled fixes (URLs, video ids, mojibake and HTML
  entities, full-width and odd characters, underscores, leading numbers, featured
  artists, remixers, titles from file names, and an opt-in case fix), tested against
  per-fix tables, a clean corpus of about 400 titles in many genres and scripts, and
  properties such as idempotence. A YAML rules file tunes or disables fixes and adds
  rules made of conditions (shared with smartlists) and `replace` or `set` actions.
  Each planned change names the fix or rule that made it (`by` in the plan JSON).
- Relocating tracks (`djlib relocate FOLDER`): tracks whose files are not on this
  computer are matched by file name under a folder (the same trailing folders win; ties
  without a recorded size are reported, never guessed) and get their new paths through a
  plan. Only the path changes, so links to beets and Mixxx items keep working.
  Imports take `--find-in FOLDER` to import only the tracks found there, and folder
  walks show their progress on standard error in terminals.
- beets libraries (`djlib import beets`): every item's tags, keys in Open Key or
  musical notation, MusicBrainz and Discogs ids and flexible attributes, from both the
  older schema and beets 2.14's list fields and relative paths. Read only; beets is not
  a dependency. Imports now link tracks to their source items (schema version 6) and
  match by that link before the path, warn about tracks whose files are not on this
  computer, and create no folder for sources without playlists.

- Exports to Mixxx (`djlib export mixxx`): track metadata, keys, cues, loops, beat
  grids, new tracks, playlists and crates are written into Mixxx 2.5 databases by
  editing a copy and replacing the file atomically, with everything djlib does not
  model kept. Writing is refused while Mixxx runs. Exports to targets that hold a
  collection merge three ways and keep fields edited in the target, reporting
  conflicts; the values written become the merge base, so importing right after an
  export changes nothing. Playlists djlib creates in Mixxx are not imported back as
  copies (schema version 5 records where each exported node lives in its target).
  Snapshots of export targets are exact byte copies.
- Mixxx adapter (read only): reads Mixxx 2.5 library databases (schema 39) from a
  consistent in-memory copy, with tracks, keys, hot cues, main cue, loops, beat grids
  (constant grids and beat maps), playlists and crates; Auto DJ and history are left out.
- Imports into the library (`djlib import mixxx`): tracks matched by path, a three-way
  merge per source that keeps edits made in djlib and reports conflicts, and the
  source's playlists in a folder of its own that re-imports replace with stable ids.
  The store keeps per-source merge bases (schema version 4).
- Plan/apply engine: the only write path. Plans list every change with before and
  after values (tracks, playlists, files, losses, warnings and conflicts) as text or
  versioned JSON. Applying needs a confirmation, refuses targets changed since the
  plan, snapshots first, writes files atomically and restores the target
  automatically on failure. Exports can write all playlists, selected ones or only
  those modified since the last export to the same target; nothing is ever deleted
  from a target. The store gains a revision counter and per-target sync state
  (schema version 3).
- Commands `djlib scan`, `djlib export m3u`, `djlib snapshot list` and `djlib
  snapshot restore`, dry-run by default with `--apply`, `--yes` and `--json`, and a
  `--home` directory (or `DJLIB_HOME`) for the library and snapshots.
- Folder scan: reads MP3, FLAC, WAV, AIFF, M4A and OGG tags and properties with
  mutagen into scan plans, with incremental rescans, move detection that keeps cues
  and playlists, missing-file marking, a three-way merge that keeps edits made in
  djlib, and non-UTF-8 file names skipped with a warning. The store keeps per-track
  file state (schema version 2) and applies scan plans atomically.
- Adapter contract: declared capabilities, read-only reading, write plans with full
  file contents, base hashes and aggregated losses, path mapping between machines,
  and an adapter registry.
- M3U/M3U8 adapter: reads playlist files and folder trees (relative and absolute
  entries, `file://` URIs, legacy encodings, unknown directives kept) and plans UTF-8
  `.m3u8` files with absolute or relative paths and folders as directories.
- Snapshots: hash-verified copies of the files an operation writes, with listing,
  verified and reversible restore (rolled back if it fails midway), consistent copies
  of SQLite databases, and per-target retention of the last 10 snapshots by default.
- Canonical library model: tracks with cues, loops, beatgrids and tags, a playlist
  tree of folders, playlists and smartlists, stable track identifiers, normalized
  paths, integer microsecond times, musical keys in Open Key and musical notation,
  and per-format `unmapped` data for lossless round-trips.
- SQLite library store with a documented schema, track and playlist operations,
  versioned migrations with a backup before each upgrade, and refusal of files from
  other applications or newer releases.
- Project bootstrap: Python package `djlib` managed with uv, placeholder `djlib`
  command (`--version`, `--help`), ruff, pyright, pytest + hypothesis,
  pre-commit hooks and CI on Linux, macOS and Windows.

### Changed

- Plan JSON version 2: track changes and conflicts name the track under `name`
  (was `label`, easy to confuse with the record label), and added tracks list every
  field they bring.
