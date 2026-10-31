"""Saving a library and loading it back returns an equal library."""

import time
from pathlib import Path

from hypothesis import HealthCheck, given, settings

from support.strategies import libraries, synthetic_library
from tunedex.model.library import Library
from tunedex.store import Store


@given(library=libraries())
@settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_any_valid_library_round_trips(tmp_path: Path, library: Library) -> None:
    # One database is reused across examples; replace_library resets it each time.
    with Store.open(tmp_path / "library.db") as store:
        store.replace_library(library)
        assert store.load_library() == library


def test_ten_thousand_tracks_round_trip(tmp_path: Path) -> None:
    library = synthetic_library(10_000)
    path = tmp_path / "library.db"

    started = time.perf_counter()
    with Store.open(path) as store:
        store.replace_library(library)
    saved = time.perf_counter()
    with Store.open(path) as store:
        loaded = store.load_library()
    finished = time.perf_counter()

    assert loaded == library
    print(f"\n10,000 tracks: save {saved - started:.2f}s, load {finished - saved:.2f}s")
