"""``tunedex write-tags`` and restoring its snapshot (specs/cli)."""

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner, Result

from support.audio import CLIPS
from support.files import sha256
from tunedex.cli import app
from tunedex.sources.tags import read_file

runner = CliRunner()


def invoke(tmp_path: Path, *arguments: str) -> Result:
    return runner.invoke(app, ["--home", str(tmp_path / "home"), *arguments])


def music(tmp_path: Path) -> Path:
    folder = tmp_path / "music" / "new"
    folder.mkdir(parents=True)
    for name in ("tagged-v24.mp3", "tagged.flac"):
        shutil.copyfile(CLIPS / name, folder / name)
    shutil.copyfile(CLIPS / "tagged.wav", tmp_path / "music" / "old.wav")
    return tmp_path / "music"


def cleaned(tmp_path: Path) -> Path:
    """A scanned folder whose tracks were cleaned by ``fix``."""
    root = music(tmp_path)
    assert invoke(tmp_path, "scan", str(root), "--apply", "--yes").exit_code == 0
    result = invoke(tmp_path, "fix", "--only", "remove_urls", "--apply", "--yes")
    assert result.exit_code == 0, result.stderr
    return root


def test_dry_run_under_a_folder(tmp_path: Path) -> None:
    root = cleaned(tmp_path)
    before = {p: sha256(p) for p in root.rglob("*.*")}

    result = invoke(tmp_path, "write-tags", "--under", str(root / "new"))

    assert result.exit_code == 0, result.stderr
    assert "Files to write: 2" in result.stdout
    assert "title: 'Galaxy [www.slider.kz]' → 'Galaxy'" in result.stdout
    assert "Dry run" in result.stdout
    assert {p: sha256(p) for p in root.rglob("*.*")} == before


def test_apply_then_undo(tmp_path: Path) -> None:
    root = cleaned(tmp_path)
    paths = sorted(root.rglob("*.*"))
    before = {p: sha256(p) for p in paths}

    result = invoke(tmp_path, "write-tags", "--apply", "--yes", "--json")

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["format"] == "tunedex-plan"
    assert document["target"] == "tags"
    assert len(document["tags"]) == 3
    assert document["result"]["status"] == "applied"
    assert document["result"]["files_written"] == 3
    assert read_file(root / "new" / "tagged.flac").values["title"] == "Galaxy"
    assert invoke(tmp_path, "scan", str(root), "--json").stdout.count('"change"') == 0

    listed = json.loads(invoke(tmp_path, "snapshot", "list", "tags", "--json").stdout)
    (snapshot,) = listed["snapshots"]
    assert snapshot["id"] == document["result"]["snapshot"]
    assert sorted(snapshot["files"]) == sorted(str(p) for p in paths)

    restored = invoke(tmp_path, "snapshot", "restore", "tags", snapshot["id"], "--apply", "--yes")

    assert restored.exit_code == 0, restored.stderr
    assert {p: sha256(p) for p in paths} == before


def test_nothing_to_write(tmp_path: Path) -> None:
    root = music(tmp_path)
    assert invoke(tmp_path, "scan", str(root), "--apply", "--yes").exit_code == 0
    result = invoke(tmp_path, "write-tags", "--apply", "--yes")
    assert result.exit_code == 0, result.stderr
    assert "Nothing to do." in result.stdout


def test_needs_yes_without_a_terminal(tmp_path: Path) -> None:
    cleaned(tmp_path)
    result = invoke(tmp_path, "write-tags", "--apply")
    assert result.exit_code == 1
    assert "pass --yes" in result.stderr
