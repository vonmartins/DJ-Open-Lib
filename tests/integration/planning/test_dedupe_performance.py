"""Timing of finding duplicates among 10,000 tracks (reported, not asserted)."""

import time

from djlib.model.library import Library
from djlib.model.track import Track
from djlib.planning import Engine
from djlib.store import Store

COUNT = 10_000


def test_dupes_timings(engine: Engine, store: Store) -> None:
    tracks = []
    for i in range(COUNT):
        song = i // 2 if i % 10 == 0 else i  # one in ten tracks has a copy
        tracks.append(
            Track(
                path_origin=f"/music/{i:05d}.mp3",
                artist=f"Artist {song % 97}",
                title=f"Track {song} (Original Mix)",
                duration_us=300_000_000 + song,
            )
        )
    store.replace_library(Library.build(tracks))  # one transaction: commits are slow on Windows

    started = time.perf_counter()
    groups = engine.find_duplicates()
    found = time.perf_counter() - started
    started = time.perf_counter()
    plan = engine.plan_merge(keep_files=True)
    planned = time.perf_counter() - started

    assert groups and not plan.empty
    print(
        f"\n{COUNT} tracks: {len(groups)} groups found {found:.2f}s, merge planned {planned:.2f}s"
    )
