"""Importing beets libraries through the engine (specs/library-import, source-beets)."""

import contextlib
import dataclasses
import sqlite3
from pathlib import Path

import pytest

from support.audio import tagged_copy
from support.beets import BeetsDatabase
from tunedex.model.key import Key, Mode
from tunedex.planning import Engine, assume_yes
from tunedex.sources.beets import BeetsSource
from tunedex.store import Store

BEETS = BeetsSource()


@pytest.fixture
def beets(tmp_path: Path) -> BeetsDatabase:
    return BeetsDatabase(tmp_path / "beets" / "library.db")


def set_column(beets: BeetsDatabase, column: str, value: object) -> None:
    with contextlib.closing(sqlite3.connect(beets.path)) as db, db:
        db.execute(f"UPDATE items SET {column} = ?", (value,))


def test_source_without_playlists(engine: Engine, store: Store, beets: BeetsDatabase) -> None:
    beets.add_item("/music/a.mp3", title="A")

    plan = engine.plan_import(BEETS, beets.path)
    engine.apply(plan, assume_yes)

    assert plan.nodes == ()
    assert store.children() == ()
    assert [t.title for t in store.list_tracks()] == ["A"]


def test_scanned_track_filled_from_beets(
    engine: Engine, store: Store, beets: BeetsDatabase, tmp_path: Path
) -> None:
    music = tmp_path / "music"
    tagged_copy(music, "mp3", name="a.mp3", title="A")
    engine.apply(engine.plan_scan(music), assume_yes)
    (scanned,) = store.list_tracks()
    beets.add_item(scanned.path, title="A", label="Ninja Tune", initial_key="1m")

    engine.apply(engine.plan_import(BEETS, beets.path), assume_yes)

    (track,) = store.list_tracks()
    assert track.id == scanned.id
    assert (track.label, track.key) == ("Ninja Tune", Key(tonic=9, mode=Mode.MINOR))


def test_changes_edits_and_reimport(engine: Engine, store: Store, beets: BeetsDatabase) -> None:
    beets.add_item("/music/a.mp3", title="A", genre="Techno", label="L1")
    engine.apply(engine.plan_import(BEETS, beets.path), assume_yes)
    (track,) = store.list_tracks()
    store.update_track(dataclasses.replace(track, genre="House"))
    set_column(beets, "genre", "Minimal")
    set_column(beets, "label", "L2")

    plan = engine.plan_import(BEETS, beets.path)
    engine.apply(plan, assume_yes)

    (after,) = store.list_tracks()
    assert (after.label, after.genre) == ("L2", "House")
    assert [(c.field, c.library_value, c.file_value) for c in plan.conflicts] == [
        ("genre", "House", "Minimal")
    ]
    assert engine.plan_import(BEETS, beets.path).empty
