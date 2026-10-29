"""Programs open the same library as the command line, without the command line."""

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import djlib
from djlib.cli import app
from support.audio import tagged_copy


@pytest.fixture
def music(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    tagged_copy(root, "mp3", name="a.mp3", title="A", artist="Artist")
    return root


def test_same_library_as_the_command_line(
    tmp_path: Path, music: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DJLIB_HOME", str(tmp_path / "h"))
    result = CliRunner().invoke(app, ["scan", str(music), "--apply", "--yes"])
    assert result.exit_code == 0

    with djlib.open_library() as engine:
        assert [t.title for t in engine.store.list_tracks()] == ["A"]


def test_home_resolution_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJLIB_HOME", str(tmp_path / "env"))
    assert djlib.resolve_home(tmp_path / "given") == tmp_path / "given"
    assert djlib.resolve_home() == tmp_path / "env"
    monkeypatch.delenv("DJLIB_HOME")
    assert djlib.resolve_home() == djlib.default_home()


def test_planning_creates_nothing_and_applying_creates_the_library(
    tmp_path: Path, music: Path
) -> None:
    home = djlib.Home(tmp_path / "new")
    with home.engine() as engine:
        plan = engine.plan_scan(music)
        assert not home.path.exists()
        result = home.apply(engine, plan)

    assert result.status == "applied"
    with djlib.open_library(home.path) as engine:
        assert len(engine.store.list_tracks()) == 1


def test_import_does_not_load_the_command_line() -> None:
    code = (
        "import sys, djlib\n"
        "print(sorted(m for m in sys.modules if m == 'typer' or m.startswith('djlib.cli')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "[]"
