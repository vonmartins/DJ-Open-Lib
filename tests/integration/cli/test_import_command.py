"""``tunedex import mixxx`` (specs/cli)."""

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from support.files import tree_bytes
from support.mixxx import MixxxDatabase
from tunedex.cli import app
from tunedex.cli.imports import default_mixxx_location
from tunedex.store import Store

runner = CliRunner()


def test_import_from_a_path(tmp_path: Path) -> None:
    database = MixxxDatabase(tmp_path / "profile" / "mixxxdb.sqlite")
    database.add_playlist("Peak", [database.add_track("/music/a.mp3", title="A")])
    database.close()
    before = tree_bytes(tmp_path / "profile")

    result = runner.invoke(
        app,
        [
            "--home",
            str(tmp_path / "home"),
            "import",
            "mixxx",
            str(database.path),
            "--apply",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert "Applied." in result.stdout
    with Store.open(tmp_path / "home" / "library.db") as store:
        assert [t.title for t in store.list_tracks()] == ["A"]
        assert [n.name for n in store.children()] == ["Mixxx"]
    assert tree_bytes(tmp_path / "profile") == before


def test_default_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    assert default_mixxx_location() == tmp_path / ".mixxx"

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert default_mixxx_location() == tmp_path / "local" / "Mixxx"

    monkeypatch.setattr(sys, "platform", "darwin")
    sandboxed = (
        tmp_path / "Library/Containers/org.mixxx.mixxx/Data/Library/Application Support/Mixxx"
    )
    assert default_mixxx_location() == sandboxed
    (tmp_path / "Library" / "Application Support" / "Mixxx").mkdir(parents=True)
    assert default_mixxx_location() == tmp_path / "Library" / "Application Support" / "Mixxx"
    sandboxed.mkdir(parents=True)
    assert default_mixxx_location() == sandboxed


def test_default_location_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    MixxxDatabase(tmp_path / ".mixxx" / "mixxxdb.sqlite").close()

    result = runner.invoke(app, ["--home", str(tmp_path / "home"), "import", "mixxx", "--json"])

    assert result.exit_code == 0, result.stderr
    assert '"title": "import mixxx from ' in result.stdout


def test_no_mixxx_library_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")

    result = runner.invoke(app, ["--home", str(tmp_path / "home"), "import", "mixxx"])

    assert result.exit_code == 1
    assert f"no Mixxx library at {tmp_path / '.mixxx'}" in result.stderr
