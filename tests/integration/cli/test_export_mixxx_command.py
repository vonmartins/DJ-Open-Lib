"""``tunedex export mixxx`` (specs/cli)."""

import contextlib
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from support.files import tree_bytes
from support.mixxx import MixxxDatabase
from tunedex.adapters.mixxx import MixxxAdapter
from tunedex.cli import app
from tunedex.cli import export as export_command
from tunedex.model.playlist import Playlist
from tunedex.model.track import Track
from tunedex.snapshots import SnapshotStore
from tunedex.store import Store

runner = CliRunner()


@pytest.fixture(autouse=True)
def mixxx_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_command, "MixxxAdapter", lambda: MixxxAdapter(running=lambda: False))


@pytest.fixture
def profile(tmp_path: Path) -> Path:
    database = MixxxDatabase(tmp_path / "profile" / "mixxxdb.sqlite")
    database.close()
    (tmp_path / "home").mkdir()
    with Store.open(tmp_path / "home" / "library.db") as store:
        track = Track(path_origin="/music/a.mp3", title="A")
        store.add_track(track)
        store.add_node(Playlist(name="Peak", entries=(track.id,)))
    return tmp_path / "profile"


def invoke(tmp_path: Path, *arguments: str) -> Result:
    return runner.invoke(app, ["--home", str(tmp_path / "home"), "export", "mixxx", *arguments])


def test_export_applied(profile: Path, tmp_path: Path) -> None:
    result = invoke(tmp_path, str(profile), "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    database = profile / "mixxxdb.sqlite"
    with contextlib.closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT name FROM Playlists WHERE hidden = 0").fetchall() == [("Peak",)]
    snapshots = SnapshotStore(tmp_path / "home" / "snapshots")
    (target,) = snapshots.targets()
    assert target.startswith("mixxx-") and len(snapshots.list(target)) == 1


def test_dry_run(profile: Path, tmp_path: Path) -> None:
    before = tree_bytes(profile)

    result = invoke(tmp_path, str(profile))

    assert result.exit_code == 0, result.stderr
    assert "Peak" in result.stdout
    assert tree_bytes(profile) == before


def test_conflicting_options(profile: Path, tmp_path: Path) -> None:
    result = invoke(tmp_path, str(profile), "--playlist", "Peak", "--modified")

    assert result.exit_code != 0


def test_mixxx_running(profile: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_command, "MixxxAdapter", lambda: MixxxAdapter(running=lambda: True))
    before = tree_bytes(profile)

    result = invoke(tmp_path, str(profile), "--apply", "--yes")

    assert result.exit_code == 1
    assert "quit Mixxx" in result.stderr
    assert tree_bytes(profile) == before
