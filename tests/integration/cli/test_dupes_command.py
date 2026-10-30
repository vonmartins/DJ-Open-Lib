"""``djlib dupes`` (specs/cli)."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from djlib.cli import _flow, app
from djlib.model.paths import normalize_path
from djlib.model.track import Track
from djlib.planning import engine as engine_module
from djlib.store import Store

runner = CliRunner()


def invoke(tmp_path: Path, *arguments: str, answers: str | None = None) -> Result:
    return runner.invoke(
        app, ["--home", str(tmp_path / "home"), "dupes", *arguments], input=answers
    )


@pytest.fixture
def trashed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    moved: list[str] = []

    def trash(path: str) -> None:
        moved.append(path)
        Path(path).unlink()

    monkeypatch.setattr(engine_module, "send2trash", trash)
    return moved


@pytest.fixture
def interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_flow, "stdin_is_interactive", lambda: True)


def library(tmp_path: Path, *groups: str) -> dict[str, Path]:
    """Two copies of each named song: a FLAC (suggested) and an MP3."""
    (tmp_path / "home").mkdir(exist_ok=True)
    music = tmp_path / "music"
    music.mkdir(exist_ok=True)
    files: dict[str, Path] = {}
    with Store.open(tmp_path / "home" / "library.db") as store:
        for title in groups:
            for kind, extra in (("flac", {}), ("mp3", {"bitrate": 320})):
                path = music / f"{title}.{kind}"
                path.write_bytes(b"audio")
                fields: dict[str, Any] = {"artist": "Phaeleh", "title": title, **extra}
                store.add_track(Track(path_origin=str(path), file_format=kind, **fields))
                files[f"{title}.{kind}"] = path
    return files


def paths(tmp_path: Path) -> list[str]:
    with Store.open(tmp_path / "home" / "library.db") as store:
        return sorted(t.path.rsplit("/", 1)[-1] for t in store.list_tracks())


def test_report(tmp_path: Path) -> None:
    library(tmp_path, "Numb")

    result = invoke(tmp_path)

    assert result.exit_code == 0, result.stderr
    assert "Phaeleh - Numb  (keep 1: lossless)" in result.stdout
    first, second = (line for line in result.stdout.splitlines() if line.startswith("  "))
    assert first.startswith("  1  *  FLAC")
    assert second.startswith("  2     MP3")
    assert "320 kbps" in second
    assert first.index("/") == second.index("/")  # the paths line up
    assert paths(tmp_path) == ["Numb.flac", "Numb.mp3"]
    document = json.loads(invoke(tmp_path, "--json").stdout)
    assert document["format"] == "djlib-dupes"
    assert [t["suggested"] for t in document["groups"][0]["tracks"]] == [True, False]


def test_merge_dry_run(tmp_path: Path, trashed: list[str]) -> None:
    library(tmp_path, "Numb")

    result = invoke(tmp_path, "--merge")

    assert result.exit_code == 0, result.stderr
    assert "merged into" in result.stdout
    assert "Files to move to the trash: 1" in result.stdout
    assert (paths(tmp_path), trashed) == (["Numb.flac", "Numb.mp3"], [])


def test_another_track_kept(tmp_path: Path, trashed: list[str]) -> None:
    files = library(tmp_path, "Numb")

    result = invoke(tmp_path, "--merge", "--keep", str(files["Numb.mp3"]), "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    assert paths(tmp_path) == ["Numb.mp3"]
    assert trashed == [str(files["Numb.flac"])]
    assert "Moved 1 file to the system trash." in result.stdout


def test_unknown_keep(tmp_path: Path) -> None:
    library(tmp_path, "Numb")

    result = invoke(tmp_path, "--merge", "--keep", str(tmp_path / "other.mp3"))

    assert result.exit_code == 1
    assert "is in no group of duplicates" in result.stderr


def test_one_group_skipped(tmp_path: Path, trashed: list[str], interactive: None) -> None:
    library(tmp_path, "Lounge", "Numb")

    result = invoke(tmp_path, "--merge", "--apply", answers="\ns\ny\n")

    assert result.exit_code == 0, result.stderr
    assert "Group 1/2: Phaeleh - Lounge" in result.stdout
    assert paths(tmp_path) == ["Lounge.flac", "Numb.flac", "Numb.mp3"]
    assert len(trashed) == 1


def test_marked_as_not_duplicates(tmp_path: Path, trashed: list[str], interactive: None) -> None:
    library(tmp_path, "Numb")

    result = invoke(tmp_path, "--merge", "--apply", answers="i\ny\n")

    assert result.exit_code == 0, result.stderr
    assert "No duplicates." in invoke(tmp_path).stdout
    assert trashed == []


def test_number_and_quit(tmp_path: Path, trashed: list[str], interactive: None) -> None:
    files = library(tmp_path, "Lounge", "Numb")

    result = invoke(tmp_path, "--merge", "--apply", answers="x\n2\nq\ny\n")

    assert result.exit_code == 0, result.stderr
    assert "a number keeps that one" in result.stdout
    assert paths(tmp_path) == ["Lounge.mp3", "Numb.flac", "Numb.mp3"]
    assert trashed == [str(files["Lounge.flac"])]


def test_declined_at_the_end(tmp_path: Path, trashed: list[str], interactive: None) -> None:
    library(tmp_path, "Numb")

    result = invoke(tmp_path, "--merge", "--apply", answers="i\nn\n")

    assert result.exit_code == 0, result.stderr
    assert "Not applied." in result.stdout
    assert "Phaeleh - Numb" in invoke(tmp_path).stdout
    assert paths(tmp_path) == ["Numb.flac", "Numb.mp3"]


def test_keep_path_is_normalized(tmp_path: Path) -> None:
    files = library(tmp_path, "Numb")

    result = invoke(tmp_path, "--merge", "--keep", str(files["Numb.mp3"]), "--json")

    document = json.loads(result.stdout)
    (merged,) = [t for t in document["tracks"] if t["change"] == "merged"]
    assert merged["path"] == normalize_path(str(files["Numb.flac"]))


def test_skip_and_ignore_without_a_terminal(tmp_path: Path, trashed: list[str]) -> None:
    files = library(tmp_path, "Ash", "Bloom", "Coil")

    result = invoke(
        tmp_path,
        "--merge",
        "--skip",
        str(files["Ash.mp3"]),
        "--ignore",
        str(files["Bloom.flac"]),
        "--apply",
        "--yes",
    )

    assert result.exit_code == 0, result.stderr
    assert paths(tmp_path) == ["Ash.flac", "Ash.mp3", "Bloom.flac", "Bloom.mp3", "Coil.flac"]
    report = json.loads(invoke(tmp_path, "--json").stdout)
    assert [g["name"] for g in report["groups"]] == ["Phaeleh - Ash"]


def test_two_answers_for_one_group(tmp_path: Path) -> None:
    files = library(tmp_path, "Ash")

    result = invoke(
        tmp_path, "--merge", "--keep", str(files["Ash.mp3"]), "--skip", str(files["Ash.flac"])
    )

    assert result.exit_code == 1
    assert "Phaeleh - Ash" in result.stderr


def test_skip_is_the_default_answer(tmp_path: Path, interactive: None) -> None:
    files = library(tmp_path, "Ash")

    result = invoke(tmp_path, "--merge", "--skip", str(files["Ash.mp3"]), "--apply", answers="\n")

    assert "Keep [s]" in result.stdout
    assert paths(tmp_path) == ["Ash.flac", "Ash.mp3"]


def test_under_keeps_groups_with_a_track_there(tmp_path: Path) -> None:
    files = library(tmp_path, "Ash")
    elsewhere = tmp_path / "elsewhere"

    inside = invoke(tmp_path, "--under", str(files["Ash.flac"].parent), "--json")
    elsewhere.mkdir()
    outside = invoke(tmp_path, "--under", str(elsewhere), "--json")

    assert len(json.loads(inside.stdout)["groups"][0]["tracks"]) == 2
    assert json.loads(outside.stdout)["groups"] == []
