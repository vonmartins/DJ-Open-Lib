"""Timing of planning fixes on 10,000 tracks (reported, not asserted)."""

import time

from tunedex.model.library import Library
from tunedex.model.track import Track
from tunedex.planning import Engine
from tunedex.rules.ruleset import defaults
from tunedex.store import Store

COUNT = 10_000


def test_fix_timings(engine: Engine, store: Store) -> None:
    tracks = []
    for i in range(COUNT):
        dirty = i % 4 == 0
        title = f"0{i % 10} - Track_{i} (freebeats.com)" if dirty else f"Track {i}"
        tracks.append(
            Track(path_origin=f"/music/{i:05d}.mp3", artist=f"Artist {i % 97}", title=title)
        )
    store.replace_library(Library.build(tracks))  # one transaction: commits are slow on Windows

    started = time.perf_counter()
    plan = engine.plan_fix(defaults())
    planned = time.perf_counter() - started

    assert len(plan.tracks) == COUNT // 4
    print(f"\n{COUNT} tracks: plan fixes {planned:.2f}s")
