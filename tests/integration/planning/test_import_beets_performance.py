"""Timing of reading and importing a 10,000-item beets library (reported, not asserted)."""

import contextlib
import sqlite3
import time
from pathlib import Path

from support.beets import BeetsDatabase
from tunedex.planning import Engine, assume_yes
from tunedex.sources.beets import BeetsSource

COUNT = 10_000


def test_beets_import_timings(tmp_path: Path, engine: Engine) -> None:
    database = BeetsDatabase(tmp_path / "library.db")
    with contextlib.closing(sqlite3.connect(database.path)) as db, db:
        db.executemany(
            "INSERT INTO items (id, path, title, artist, genre, bpm, initial_key, length,"
            " bitrate, samplerate, added, mb_trackid) VALUES (?, ?, ?, ?, 'Techno', 128, '1m',"
            " 300.0, 320000, 44100, 1771541731.9, ?)",
            (
                (i, f"/music/{i:05d}.mp3".encode(), f"Track {i}", f"Artist {i % 97}", f"mb-{i}")
                for i in range(1, COUNT + 1)
            ),
        )
        db.executemany(
            "INSERT INTO item_attributes (entity_id, key, value) VALUES (?, 'data_source', ?)",
            ((i, "MusicBrainz") for i in range(1, COUNT + 1)),
        )
    source = BeetsSource()

    started = time.perf_counter()
    source.read(database.path)
    read = time.perf_counter() - started
    started = time.perf_counter()
    plan = engine.plan_import(source, database.path)
    planned = time.perf_counter() - started
    started = time.perf_counter()
    engine.apply(plan, assume_yes)
    applied = time.perf_counter() - started
    started = time.perf_counter()
    again = engine.plan_import(source, database.path)
    replanned = time.perf_counter() - started

    assert len(plan.tracks) == COUNT and again.empty
    print(
        f"\n{COUNT} beets items: read {read:.2f}s, plan {planned:.2f}s,"
        f" apply {applied:.2f}s, re-plan {replanned:.2f}s"
    )
