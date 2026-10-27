# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
