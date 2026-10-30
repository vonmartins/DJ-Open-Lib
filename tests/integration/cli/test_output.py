"""Colored output is the plain output plus escape codes (specs/cli-presentation)."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from djlib.cli import app
from djlib.model.track import Track
from djlib.store import Store
from support.audio import tagged_copy

ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
runner = CliRunner()


def djlib(home: Path, *args: str, color: bool) -> Result:
    env = {"FORCE_COLOR": "1"} if color else {"NO_COLOR": "1"}
    return runner.invoke(app, ["--home", str(home), *args], env=env)


@pytest.fixture
def music(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    tagged_copy(root, "mp3", name="a.mp3", title="Rise [x1]", artist="Velk")
    tagged_copy(root, "flac", name="b.flac", title="Rise [x1]", artist="Velk")
    tagged_copy(root, "mp3", name="c.mp3", title="Fall", artist="Arno")
    return root


def test_added_tracks_are_colored(tmp_path: Path, music: Path) -> None:
    out = djlib(tmp_path / "home", "scan", str(music), color=True).stdout

    added = next(line for line in out.splitlines() if "a.mp3" in line)
    assert added.startswith("\x1b[32m")  # green


def test_no_color_option_wins(tmp_path: Path, music: Path) -> None:
    result = runner.invoke(
        app,
        ["--no-color", "--home", str(tmp_path / "home"), "scan", str(music)],
        env={"FORCE_COLOR": "1"},
    )

    assert result.exit_code == 0
    assert "\x1b" not in result.stdout


@pytest.mark.parametrize(
    "command", [["scan", "MUSIC"], ["list"], ["dupes"], ["status"], ["playlists"], ["fix"]]
)
def test_color_only_adds_escape_codes(tmp_path: Path, music: Path, command: list[str]) -> None:
    home = tmp_path / "home"
    djlib(home, "scan", str(music), "--apply", "--yes", color=False)
    (music / "d.mp3").write_bytes((music / "c.mp3").read_bytes())  # something left to scan
    arguments = [str(music) if a == "MUSIC" else a for a in command]

    colored = djlib(home, *arguments, color=True)
    plain = djlib(home, *arguments, color=False)

    assert colored.exit_code == plain.exit_code == 0, plain.stderr
    assert "\x1b" not in plain.stdout
    if command != ["playlists"]:  # an empty tree has nothing to color
        assert ESCAPE.search(colored.stdout)
    assert ESCAPE.sub("", colored.stdout) == plain.stdout


def test_errors_are_colored_and_stay_one_line(tmp_path: Path) -> None:
    result = djlib(tmp_path / "home", "list", "--under", str(tmp_path / "nowhere"), color=True)

    assert result.exit_code == 1
    assert result.stderr.startswith("\x1b[1;31merror:")
    assert ESCAPE.sub("", result.stderr).count("\n") == 1


def test_long_paths_are_printed_whole(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = "/music/" + "deep/" * 50 + "a.mp3"
    with Store.open(home / "library.db") as store:
        store.add_track(Track(path_origin=path, title="Rise"))

    out = ESCAPE.sub("", djlib(home, "list", color=True).stdout)

    assert len(path) > 200
    assert any(line.endswith(f"  {path}") for line in out.splitlines())


def test_help_lists_no_color() -> None:
    assert "--no-color" in runner.invoke(app, ["--help"], env={"NO_COLOR": "1"}).stdout
