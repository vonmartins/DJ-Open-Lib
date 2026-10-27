"""Applying an export and planning it again gives an empty plan, whatever the library."""

import tempfile
from pathlib import Path

from hypothesis import given, settings

from djlib.adapters.m3u import M3UAdapter
from djlib.model.library import Library
from djlib.planning import Engine, assume_yes
from djlib.snapshots import SnapshotStore
from djlib.store import Store
from support.strategies import libraries


@given(library=libraries())
@settings(max_examples=40, deadline=None)
def test_export_then_replan_is_empty(library: Library) -> None:
    # A fresh directory per example: leftovers from earlier examples would be read back.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with Store.open(root / "library.db") as store:
            store.replace_library(library)
            engine = Engine(store, SnapshotStore(root / "snapshots"))
            out = root / "out"

            result = engine.apply(engine.plan_export(M3UAdapter(), out), assume_yes)

            assert result.status in {"applied", "nothing"}
            assert engine.plan_export(M3UAdapter(), out).empty
            if result.status == "applied":
                assert engine.plan_export(M3UAdapter(), out, modified_only=True).empty
