"""Timing of planning fixes on 10,000 tracks (reported, not asserted)."""

import time

from djlib.model.track import Track
from djlib.planning import Engine
from djlib.rules.ruleset import defaults
from djlib.store import Store

COUNT = 10_000


def test_fix_timings(engine: Engine, store: Store) -> None:
    for i in range(COUNT):
        dirty = i % 4 == 0
        title = f"0{i % 10} - Track_{i} (freebeats.com)" if dirty else f"Track {i}"
        store.add_track(
            Track(path_origin=f"/music/{i:05d}.mp3", artist=f"Artist {i % 97}", title=title)
        )

    started = time.perf_counter()
    plan = engine.plan_fix(defaults())
    planned = time.perf_counter() - started

    assert len(plan.tracks) == COUNT // 4
    print(f"\n{COUNT} tracks: plan fixes {planned:.2f}s")
