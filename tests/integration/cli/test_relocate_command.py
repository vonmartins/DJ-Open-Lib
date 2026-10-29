"""``djlib relocate`` (specs/cli)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from djlib.cli import _flow as flow
from djlib.cli import app
from djlib.model.paths import normalize_path
from djlib.model.track import Track
from djlib.store import Store

runner = CliRunner()


def invoke(tmp_path: Path, *arguments: str) -> Result:
    return runner.invoke(app, ["--home", str(tmp_path / "home"), "relocate", *arguments])


def library(tmp_path: Path) -> Path:
    (tmp_path / "home").mkdir()
    with Store.open(tmp_path / "home" / "library.db") as store:
        store.add_track(Track(path_origin="/mnt/Elements/Music/Calyx/x.mp3", title="X"))
    file = tmp_path / "Elements" / "Music" / "Calyx" / "x.mp3"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"x")
    return file


def paths(tmp_path: Path) -> list[str]:
    with Store.open(tmp_path / "home" / "library.db") as store:
        return [t.path for t in store.list_tracks()]


def test_relocate_applied(tmp_path: Path) -> None:
    file = library(tmp_path)

    result = invoke(tmp_path, str(tmp_path / "Elements" / "Music"), "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    assert paths(tmp_path) == [normalize_path(str(file))]


def test_dry_run(tmp_path: Path) -> None:
    library(tmp_path)

    result = invoke(tmp_path, str(tmp_path / "Elements"))

    assert result.exit_code == 0, result.stderr
    assert "/mnt/Elements/Music/Calyx/x.mp3 →" in result.stdout
    assert paths(tmp_path) == ["/mnt/Elements/Music/Calyx/x.mp3"]


def test_folder_missing(tmp_path: Path) -> None:
    result = invoke(tmp_path, str(tmp_path / "nowhere"))

    assert result.exit_code == 1
    assert "nowhere is not a directory" in result.stderr


def test_not_a_terminal(tmp_path: Path) -> None:
    library(tmp_path)

    result = invoke(tmp_path, str(tmp_path / "Elements"), "--json")

    assert result.exit_code == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout)["format"] == "djlib-plan"


def test_progress_in_a_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library(tmp_path)
    monkeypatch.setattr(flow, "stderr_is_interactive", lambda: True)

    result = invoke(tmp_path, str(tmp_path / "Elements"))

    assert result.exit_code == 0, result.stderr
    assert "Searching " in result.stderr and ": 1 files" in result.stderr
    assert result.stderr.endswith("\r\x1b[K")  # cleared before the plan
    assert "Searching" not in result.stdout
