"""Timing of planning enrichment of 1000 tracks with a fake transport (reported, not asserted)."""

import time
from pathlib import Path

from support.enrich import FakeClock, FakeFpcalc, catalogue, fixture
from tunedex.enrich.cache import Cache
from tunedex.enrich.service import Services
from tunedex.model.library import Library
from tunedex.model.track import Track
from tunedex.planning import Engine
from tunedex.store import Store

COUNT = 1000


def test_enrich_timings(engine: Engine, store: Store, tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    prints: dict[str, tuple[float, str]] = {}
    tracks = []
    for i in range(COUNT):
        name = f"{i:04d}.mp3"
        (music / name).write_bytes(b"audio")
        prints[name] = (370.9, f"fp-{i}")
        # Titled like the recording AcoustID answers, so that it fits the track.
        tracks.append(Track(path_origin=str(music / name), title=f"Headspace {i}"))
    store.replace_library(Library.build(tracks))  # one transaction: commits are slow on Windows
    answer = fixture("acoustid-dfrnt.json")
    transport = catalogue({fp: answer for _duration, fp in prints.values()})
    clock = FakeClock()

    with Cache(tmp_path / "cache.db") as cache:
        services = Services.create(
            cache,
            transport=transport,
            clock=clock,
            sleep=clock.sleep,
            run=FakeFpcalc(prints),
            which=lambda _name: "/usr/bin/fpcalc",
        )
        started = time.perf_counter()
        plan = engine.plan_enrich(services)
        planned = time.perf_counter() - started

    assert len(plan.tracks) == COUNT
    print(
        f"\n{COUNT} tracks: plan enrichment {planned:.2f}s"
        f" (rate limits would add {clock.now / 60:.0f} min)"
    )
