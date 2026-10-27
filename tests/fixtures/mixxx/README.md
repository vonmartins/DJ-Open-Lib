# Mixxx fixtures

- `schema-39.sql`: the schema of a fresh Mixxx 2.5.6 library database
  (`sqlite3 mixxxdb.sqlite .schema`) plus its schema version settings. Tests build
  synthetic databases from it with `tests/support/mixxx.py`.
- `real-2.5.6.sqlite`: a real Mixxx 2.5.6 database, made by hand in a scratch profile
  (`mixxx --settingsPath <dir>`) with 15 MP3 files (44.1 kHz), then sanitized with
  `sanitize.sql`: paths are `/music/NN.mp3`, artists and titles are `Artist NN` /
  `Track NN`, other texts, cover art, waveform and analysis caches and index statistics
  are removed. Keys, BPMs, grids, cues, playlists and crates are as Mixxx wrote them.

## What `real-2.5.6.sqlite` contains

Track `/music/01.mp3` (140 BPM, key text `2m`, key id 17 = E minor):

| Cue | How it was set | Stored (engine samples) | Expected |
|---|---|---|---|
| hot cue pad 1 (slot 0) | quantize off, at 0:30.000 by hand | 2,646,858.62 | 30,009,735 µs |
| hot cue pad 2 (slot 1) | quantize on, snapped to a beat | 13,629,032 | 154,524,172 µs = first beat + 360 beats |
| loop on pad 3 (slot 2) | 4 beats, quantized | 16,086,032 + 151,200 | 182,381,315 – 184,095,601 µs |
| saved loop (no pad) | Mixxx keeps the last loop | same as above | same as above |
| main cue | set by analysis | 1,896 | 21,497 µs (memory cue) |
| intro start / outro end | set by analysis | 1,896 / −1 + 28,440,834 | 21,497 µs / 322,458,424 µs |

The beat grid is `BeatGrid-2.0` with 140 BPM and its first beat at frame 10,516
(238,458 µs). This settles the units: cue positions count both stereo channels (frames
× 2), and grid positions count frames.

Playlists: `Warmup` (6 tracks) and `Peak` (5 tracks); crate `Techno` (empty); the Auto
DJ queue and one history session (`2026-10-27`, 1 track).
