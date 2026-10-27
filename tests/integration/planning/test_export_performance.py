"""Timing of planning, applying and re-planning a 10,000-track M3U export (not asserted)."""

import time
from pathlib import Path

from djlib.adapters.m3u import M3UAdapter
from djlib.planning import Engine, assume_yes
from djlib.store import Store
from support.strategies import synthetic_library

COUNT = 10_000


def test_export_timings(tmp_path: Path, store: Store, engine: Engine) -> None:
    store.replace_library(synthetic_library(COUNT))
    out = tmp_path / "out"

    started = time.perf_counter()
    plan = engine.plan_export(M3UAdapter(), out)
    planned = time.perf_counter() - started
    engine.apply(plan, assume_yes)
    started = time.perf_counter()
    replan = engine.plan_export(M3UAdapter(), out)
    replanned = time.perf_counter() - started
    started = time.perf_counter()
    modified = engine.plan_export(M3UAdapter(), out, modified_only=True)
    modified_time = time.perf_counter() - started

    assert not plan.empty and replan.empty and modified.empty
    print(
        f"\n{COUNT} tracks, {len(plan.files)} playlists: plan {planned:.2f}s,"
        f" re-plan {replanned:.2f}s, modified re-plan {modified_time:.2f}s"
    )
