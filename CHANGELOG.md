# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
