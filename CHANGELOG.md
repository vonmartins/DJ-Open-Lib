# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
