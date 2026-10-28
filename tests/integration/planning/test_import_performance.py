"""Timing of reading and importing a 10,000-track Mixxx library (reported, not asserted)."""

import time
from pathlib import Path

from djlib.adapters.mixxx import MixxxAdapter
from djlib.planning import Engine, assume_yes
from support.mixxx import HOT_CUE, MixxxDatabase, beat_grid

COUNT = 10_000


def test_import_timings(tmp_path: Path, engine: Engine) -> None:
    database = MixxxDatabase(tmp_path / "mixxxdb.sqlite")
    db = database.db
    db.executemany(
        "INSERT INTO track_locations (id, location, filename, directory, fs_deleted)"
        " VALUES (?, ?, ?, '/music', 0)",
        ((i, f"/music/{i:05d}.mp3", f"{i:05d}.mp3") for i in range(1, COUNT + 1)),
    )
    db.executemany(
        "INSERT INTO library (id, location, artist, title, bpm, key_id, samplerate, duration,"
        " beats, beats_version, mixxx_deleted) VALUES (?, ?, ?, ?, 128.0, ?, 44100, 300, ?,"
        " 'BeatGrid-2.0', 0)",
        (
            (i, i, f"Artist {i % 97}", f"Track {i}", i % 24 + 1, beat_grid(128.0, 1000))
            for i in range(1, COUNT + 1)
        ),
    )
    db.executemany(
        "INSERT INTO cues (track_id, type, position, hotcue) VALUES (?, ?, ?, 0)",
        ((i, HOT_CUE, 88200) for i in range(1, COUNT + 1)),
    )
    db.commit()
    for p in range(20):
        database.add_playlist(f"Playlist {p}", list(range(p + 1, COUNT, 20))[:200])
    database.close()

    started = time.perf_counter()
    MixxxAdapter().read(database.path)
    read = time.perf_counter() - started
    started = time.perf_counter()
    plan = engine.plan_import(MixxxAdapter(), database.path)
    planned = time.perf_counter() - started
    started = time.perf_counter()
    engine.apply(plan, assume_yes)
    applied = time.perf_counter() - started
    started = time.perf_counter()
    again = engine.plan_import(MixxxAdapter(), database.path)
    replanned = time.perf_counter() - started

    assert len(plan.tracks) == COUNT and again.empty
    print(
        f"\n{COUNT} Mixxx tracks: read {read:.2f}s, plan {planned:.2f}s,"
        f" apply {applied:.2f}s, re-plan {replanned:.2f}s"
    )
