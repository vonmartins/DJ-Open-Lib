"""Timing of relocating 10,000 missing tracks in a 20,000-file tree (reported, not asserted)."""

import time
from pathlib import Path

from djlib.model.library import Library
from djlib.model.track import Track
from djlib.planning import Engine, assume_yes
from djlib.store import Store

COUNT = 10_000


def test_relocate_timings(tmp_path: Path, engine: Engine, store: Store) -> None:
    music = tmp_path / "music"
    for i in range(2 * COUNT):
        folder = music / f"Artist {i % 500:03d}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{i:05d}.mp3").write_bytes(b"")
    store.replace_library(  # one transaction: commits are slow on Windows
        Library.build(
            Track(path_origin=f"/mnt/server/music/Artist {i % 500:03d}/{i:05d}.mp3")
            for i in range(COUNT)
        )
    )

    started = time.perf_counter()
    plan = engine.plan_relocate(music)
    planned = time.perf_counter() - started
    started = time.perf_counter()
    engine.apply(plan, assume_yes)
    applied = time.perf_counter() - started

    assert len(plan.tracks) == COUNT
    print(f"\n{COUNT} missing tracks, {2 * COUNT} files: plan {planned:.2f}s, apply {applied:.2f}s")
