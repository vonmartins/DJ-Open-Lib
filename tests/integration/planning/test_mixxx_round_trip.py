"""Import from Mixxx, edit in djlib, export back: the whole loop through the engine."""

import contextlib
import dataclasses
import sqlite3
from pathlib import Path

import pytest

from djlib.adapters.errors import AdapterError
from djlib.adapters.mixxx import MixxxAdapter
from djlib.model.cue import Cue, CueKind
from djlib.model.playlist import Folder, Playlist
from djlib.planning import Engine, StaleTargetError, assume_yes
from djlib.snapshots import SnapshotStore
from djlib.store import Store

FIXTURE = Path(__file__).parents[2] / "fixtures" / "mixxx" / "real-2.5.6.sqlite"


class Probe:
    def __init__(self) -> None:
        self.running = False

    def __call__(self) -> bool:
        return self.running


@pytest.fixture
def probe() -> Probe:
    return Probe()


@pytest.fixture
def mixxx(probe: Probe) -> MixxxAdapter:
    return MixxxAdapter(running=probe)


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "profile" / "mixxxdb.sqlite"
    path.parent.mkdir()
    path.write_bytes(FIXTURE.read_bytes())
    return path


def imported(engine: Engine, mixxx: MixxxAdapter, database: Path) -> None:
    assert engine.apply(engine.plan_import(mixxx, database), assume_yes).status == "applied"


def edited(store: Store) -> Playlist:
    """Retitle track 01, give it a new hot cue, and put it in a new playlist Techno/Peak."""
    track = next(t for t in store.list_tracks() if t.path == "/music/01.mp3")
    cue = Cue(kind=CueKind.HOT, start_us=60_000_000, slot=5, color="#00FF00")
    store.update_track(dataclasses.replace(track, title="Retitled", cues=(*track.cues, cue)))
    peak = Playlist(name="Peak", entries=(track.id,))
    store.add_node(Folder(name="Techno", children=(peak,)))
    return peak


def test_import_after_export(
    engine: Engine, store: Store, mixxx: MixxxAdapter, database: Path
) -> None:
    imported(engine, mixxx, database)
    edited(store)

    export = engine.plan_export(mixxx, database)
    (change,) = export.tracks
    assert [f.field for f in change.fields] == ["title", "cues"]
    assert engine.apply(export, assume_yes).status == "applied"

    with contextlib.closing(sqlite3.connect(database)) as db, db:
        assert ("Retitled",) in db.execute("SELECT title FROM library").fetchall()
        assert ("Techno / Peak",) in db.execute("SELECT name FROM Playlists").fetchall()
    again = engine.plan_import(mixxx, database)
    assert (again.tracks, again.nodes, again.conflicts) == ((), (), ())
    assert engine.plan_export(mixxx, database).empty


def test_snapshot_restores_the_previous_database(
    engine: Engine, store: Store, snapshots: SnapshotStore, mixxx: MixxxAdapter, database: Path
) -> None:
    imported(engine, mixxx, database)
    edited(store)
    before = database.read_bytes()

    result = engine.apply(engine.plan_export(mixxx, database), assume_yes)

    assert database.read_bytes() != before
    plan_target = engine.plan_export(mixxx, database).target
    assert result.snapshot is not None
    snapshots.restore(snapshots.get(plan_target, result.snapshot))
    assert database.read_bytes() == before


def test_stale_database_refused(
    engine: Engine, store: Store, mixxx: MixxxAdapter, database: Path
) -> None:
    imported(engine, mixxx, database)
    edited(store)
    plan = engine.plan_export(mixxx, database)
    with contextlib.closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE library SET timesplayed = timesplayed + 1")
    changed = database.read_bytes()

    with pytest.raises(StaleTargetError):
        engine.apply(plan, assume_yes)

    assert database.read_bytes() == changed


def test_mixxx_started_after_planning(
    engine: Engine,
    store: Store,
    snapshots: SnapshotStore,
    probe: Probe,
    mixxx: MixxxAdapter,
    database: Path,
) -> None:
    imported(engine, mixxx, database)
    edited(store)
    plan = engine.plan_export(mixxx, database)
    before, snapshots_before = database.read_bytes(), snapshots.list(plan.target)
    probe.running = True

    with pytest.raises(AdapterError, match="quit Mixxx"):
        engine.apply(plan, assume_yes)

    assert database.read_bytes() == before
    assert snapshots.list(plan.target) == snapshots_before


def test_mixxx_edit_respected(
    engine: Engine, store: Store, mixxx: MixxxAdapter, database: Path
) -> None:
    imported(engine, mixxx, database)
    track = next(t for t in store.list_tracks() if t.path == "/music/02.mp3")
    store.update_track(dataclasses.replace(track, genre="House"))
    with contextlib.closing(sqlite3.connect(database)) as db, db:
        db.execute(
            "UPDATE library SET genre = 'Minimal' WHERE location ="
            " (SELECT id FROM track_locations WHERE location = '/music/02.mp3')"
        )

    plan = engine.plan_export(mixxx, database)
    engine.apply(plan, assume_yes)

    assert [(c.field, c.library_value, c.file_value) for c in plan.conflicts] == [
        ("genre", "House", "Minimal")
    ]
    with contextlib.closing(sqlite3.connect(database)) as db, db:
        assert ("Minimal",) in db.execute("SELECT genre FROM library").fetchall()
