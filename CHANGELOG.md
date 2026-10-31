# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-31

The first release. tunedex scans your music folder and imports Mixxx and beets
libraries read-only, cleans tags with bundled fixes and your own rules, takes tags from
MusicBrainz, merges duplicates, writes the clean tags back into your files, renames them,
and exports playlists to Mixxx and M3U. Every write is planned first and covered by a
snapshot you can restore.

### Added

- Writing tags to files (`tunedex write-tags`): the library's title, artist, album,
  album artist, genre, year, track and disc number, BPM, key, composer, remixer, label,
  comment, grouping and lyricist go into the files whose tags differ, as ID3v2.3 for
  MP3, WAV and AIFF and Vorbis comments for FLAC. Cover art and every other tag are kept,
  and the audio is checked unchanged before each file is replaced. Files changed since
  the last scan are skipped. The `tags` snapshot holds only the bytes outside the audio
  and restores each file byte for byte. The plan JSON lists the files in `tags`, with
  `snapshot_bytes`.
- Renaming files from their tags (`tunedex rename`): a pattern such as
  `{artist} - {title}{ (remixer remix)}`, from `--pattern` or the `rename` section of the
  rules file, gives each file a new name in its folder, safe on every system. Names
  already taken are skipped, the library follows the new names, the plan warns about
  apps that still list the old ones, and the `renames` snapshot renames them back. The
  plan result has `files_renamed`, and the restore JSON lists `renames`.
- Two fixes: `split_artist_title` (`Sam Paganini - Galaxy` in the title, no artist) and
  `remove_itunes_data` (iTunes volume data in the comment). `title_from_file_name` restores
  titles cut at 30 characters, `remove_leading_number` removes store ids, `remove_urls`
  removes a domain at the end, and `extract_featured` takes `feat` without a period.
- `--no-color` is also accepted after the command name.

- A documentation site at <https://vonmartins.github.io/tunedex/>: install, a
  tutorial, guides, the reference of every command, JSON format, error code and Python
  name, and explanations of how tunedex works. The README is now a short overview.
- Browsing the library: `tunedex status` (summary), `tunedex list` (tracks, filtered with
  `--where "FIELD OP VALUE"`, `--under`, `--playlist` and `--missing`), `tunedex show
  TRACK` (one track, by path or id) and `tunedex playlists` (the tree with track counts),
  all with `--json`. They never write.
- `--under FOLDER` on `fix` and `dupes`, `--skip` and `--ignore` on `dupes --merge`, and
  a repeatable `fix --only`.
- With `--json`, errors are printed as a JSON document with a stable `code`.
- A Python API: `tunedex.open_library()` opens the library of the command line's home, and
  `tunedex` exports the stable names.
- Help texts in one format, with an example per command, grouped in the root help, which
  also states the dry-run rule and the exit codes (0, 1 and 2).
- Colored output in terminals (plan changes by kind, warnings, errors, headers), off when
  the output is not a terminal, with `--no-color` or with `NO_COLOR`; `FORCE_COLOR`
  turns it on. Color never changes the text. Plans show each field's value before in
  red and after in green; `tunedex list` and `tunedex show` color keys by their place on
  the key wheel (in terminals with 256 colors or more). `tunedex dupes`, `tunedex snapshot
  list` and `tunedex status` print aligned columns, aligned by screen width so titles with
  wide characters no longer shift them.
- Progress displays on standard error in terminals: a spinner with the files found
  while walking folders, and a bar for `tunedex enrich`.

- Merging duplicates (`tunedex dupes`): tracks that are the same song (same MusicBrainz
  recording, or same normalized artist and title with lengths within 3 seconds; versions
  stay apart) are reported with their format, bitrate, cues and playlists and a
  suggested track to keep. `--merge` asks group by group, then plans one merge: the kept
  track inherits empty fields, cues, playlist entries, plays and tags, and the other
  files go to the system trash (`--keep-files` to keep them). Merges and groups marked
  as not duplicates are remembered (schema version 7), so imports and scans do not bring
  them back. Plans can now move audio files to the trash; the plan JSON is version 3,
  with the `merged` track change, `merged_into` and `trash`.
- Enriching tags (`tunedex enrich`): tracks are fingerprinted with `fpcalc`, recognized
  by AcoustID and tagged from MusicBrainz (title, artist, remixer, album, dates, label,
  track and disc numbers; the genre only when empty), through a plan where each change
  is marked `musicbrainz`. The first run normalizes; later runs keep edits made in
  tunedex. Ambiguous, unknown and disagreeing tracks are reported, never guessed.
  Answers are cached in the tunedex home (`--refresh` asks again), `--under FOLDER`
  limits the run, and no other command uses the network.
- Cleaning tags (`tunedex fix`): ten bundled fixes (URLs, video ids, mojibake and HTML
  entities, full-width and odd characters, underscores, leading numbers, featured
  artists, remixers, titles from file names, and an opt-in case fix), tested against
  per-fix tables, a clean corpus of about 400 titles in many genres and scripts, and
  properties such as idempotence. A YAML rules file tunes or disables fixes and adds
  rules made of conditions (shared with smartlists) and `replace` or `set` actions.
  Each planned change names the fix or rule that made it (`by` in the plan JSON).
- Relocating tracks (`tunedex relocate FOLDER`): tracks whose files are not on this
  computer are matched by file name under a folder (the same trailing folders win; ties
  without a recorded size are reported, never guessed) and get their new paths through a
  plan. Only the path changes, so links to beets and Mixxx items keep working.
  Imports take `--find-in FOLDER` to import only the tracks found there, and folder
  walks show their progress on standard error in terminals.
- beets libraries (`tunedex import beets`): every item's tags, keys in Open Key or
  musical notation, MusicBrainz and Discogs ids and flexible attributes, from both the
  older schema and beets 2.14's list fields and relative paths. Read only; beets is not
  a dependency. Imports now link tracks to their source items (schema version 6) and
  match by that link before the path, warn about tracks whose files are not on this
  computer, and create no folder for sources without playlists.

- Exports to Mixxx (`tunedex export mixxx`): track metadata, keys, cues, loops, beat
  grids, new tracks, playlists and crates are written into Mixxx 2.5 databases by
  editing a copy and replacing the file atomically, with everything tunedex does not
  model kept. Writing is refused while Mixxx runs. Exports to targets that hold a
  collection merge three ways and keep fields edited in the target, reporting
  conflicts; the values written become the merge base, so importing right after an
  export changes nothing. Playlists tunedex creates in Mixxx are not imported back as
  copies (schema version 5 records where each exported node lives in its target).
  Snapshots of export targets are exact byte copies.
- Mixxx adapter (read only): reads Mixxx 2.5 library databases (schema 39) from a
  consistent in-memory copy, with tracks, keys, hot cues, main cue, loops, beat grids
  (constant grids and beat maps), playlists and crates; Auto DJ and history are left out.
- Imports into the library (`tunedex import mixxx`): tracks matched by path, a three-way
  merge per source that keeps edits made in tunedex and reports conflicts, and the
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
- Commands `tunedex scan`, `tunedex export m3u`, `tunedex snapshot list` and `tunedex
  snapshot restore`, dry-run by default with `--apply`, `--yes` and `--json`, and a
  `--home` directory (or `TUNEDEX_HOME`) for the library and snapshots.
- Folder scan: reads MP3, FLAC, WAV, AIFF, M4A and OGG tags and properties with
  mutagen into scan plans, with incremental rescans, move detection that keeps cues
  and playlists, missing-file marking, a three-way merge that keeps edits made in
  tunedex, and non-UTF-8 file names skipped with a warning. The store keeps per-track
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
- Project bootstrap: Python package `tunedex` managed with uv, placeholder `tunedex`
  command (`--version`, `--help`), ruff, pyright, pytest + hypothesis,
  pre-commit hooks and CI on Linux, macOS and Windows.

### Fixed

- iTunes data in ID3 comment frames (`iTunNORM`, `iTunSMPB`) is no longer read as the
  track's comment.
- A scan no longer fails when two file names differ only in their Unicode form; the second
  is skipped with a warning.
- Track number, disc number, year and BPM 0 are read as empty, without warnings.
- `enrich` no longer takes a recording that does not fit the track's own artist or title;
  it reports it instead.
- `underscores_to_spaces` no longer breaks URLs into words.

### Changed

- **Breaking:** `tunedex snapshot restore TARGET ID` shows what it would restore and
  writes nothing without `--apply`, like the other commands. It also accepts `--json`.
- Every path argument and option expands `~`. A folder that does not exist is reported
  as such by every command.
- `tunedex list` shows paths relative to the folder all the listed tracks share, named on
  the last line (`46 tracks in ~/Music/`); `--json` keeps the full paths.
- BPM is shown with at most two decimals and no trailing zeros (`128`, `127.5`) in every
  command; `tunedex list` showed `128.0`.

- Plan JSON version 2: track changes and conflicts name the track under `name`
  (was `label`, easy to confuse with the record label), and added tracks list every
  field they bring.

[Unreleased]: https://github.com/vonmartins/tunedex/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/vonmartins/tunedex/releases/tag/v0.1.0
