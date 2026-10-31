"""``tunedex rename`` and restoring its snapshot (specs/cli)."""

import json
from pathlib import Path

from typer.testing import CliRunner, Result

from support.audio import tagged_copy
from tunedex.cli import app
from tunedex.model.paths import normalize_path
from tunedex.store import Store

runner = CliRunner()


def invoke(tmp_path: Path, *arguments: str) -> Result:
    return runner.invoke(app, ["--home", str(tmp_path / "home"), *arguments])


def scanned(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    tagged_copy(
        root / "dl",
        "mp3",
        "sam_paganini-galaxy_www.slider.kz.mp3",
        artist="Sam Paganini",
        title="Galaxy",
        date="2012",
    )
    tagged_copy(root / "kept", "flac", "01.flac", artist="Bicep", title="Glue")
    result = invoke(tmp_path, "scan", str(root), "--apply", "--yes")
    assert result.exit_code == 0, result.stderr
    return root


def names(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def paths(tmp_path: Path) -> list[str]:
    with Store.open(tmp_path / "home" / "library.db") as store:
        return sorted(t.path for t in store.list_tracks())


def test_dry_run_with_a_pattern(tmp_path: Path) -> None:
    root = scanned(tmp_path)
    before = names(root)

    result = invoke(
        tmp_path, "rename", "--under", str(root / "dl"), "--pattern", "{artist} - {title}"
    )

    assert result.exit_code == 0, result.stderr
    assert "sam_paganini-galaxy_www.slider.kz.mp3 → " in result.stdout
    assert "Sam Paganini - Galaxy.mp3" in result.stdout
    assert "01.flac" not in result.stdout
    assert names(root) == before


def test_pattern_from_the_rules_file(tmp_path: Path) -> None:
    root = scanned(tmp_path)
    (tmp_path / "home" / "rules.yaml").write_text(
        "rename: {pattern: '{artist} - {title} [{year}]'}\n", encoding="utf-8"
    )
    result = invoke(tmp_path, "rename", "--under", str(root / "dl"), "--json")
    assert result.exit_code == 0, result.stderr
    (track,) = json.loads(result.stdout)["tracks"]
    assert track["path"].endswith(" [2012].mp3")


def test_unknown_field(tmp_path: Path) -> None:
    scanned(tmp_path)
    result = invoke(tmp_path, "rename", "--pattern", "{artist} - {name}", "--json")
    assert result.exit_code == 1
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "plan_error"
    assert "'name'" in error["message"]
    assert result.stdout == ""


def test_apply_then_undo(tmp_path: Path) -> None:
    root = scanned(tmp_path)
    before, library = names(root), paths(tmp_path)

    result = invoke(tmp_path, "rename", "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    assert "Renamed 2 files." in result.stdout
    assert names(root) == ["dl/Sam Paganini - Galaxy.mp3", "kept/Bicep - Glue.flac"]
    assert paths(tmp_path) == sorted(normalize_path(str(root / n)) for n in names(root))
    scan = json.loads(invoke(tmp_path, "scan", str(root), "--json").stdout)
    assert scan["empty"]

    listed = json.loads(invoke(tmp_path, "snapshot", "list", "renames", "--json").stdout)
    (snapshot,) = listed["snapshots"]
    shown = invoke(tmp_path, "snapshot", "restore", "renames", snapshot["id"], "--json")
    assert len(json.loads(shown.stdout)["renames"]) == 2

    restored = invoke(
        tmp_path, "snapshot", "restore", "renames", snapshot["id"], "--apply", "--yes"
    )

    assert restored.exit_code == 0, restored.stderr
    assert names(root) == before
    assert paths(tmp_path) == library
