"""``djlib fix`` (specs/cli)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from djlib.cli import app
from djlib.model.paths import normalize_path
from djlib.model.track import Track
from djlib.store import Store

runner = CliRunner()


def library(tmp_path: Path, *tracks: Track) -> None:
    (tmp_path / "home").mkdir(exist_ok=True)
    with Store.open(tmp_path / "home" / "library.db") as store:
        for track in tracks:
            store.add_track(track)


def invoke(tmp_path: Path, *arguments: str) -> Result:
    return runner.invoke(app, ["--home", str(tmp_path / "home"), "fix", *arguments])


def tracks(tmp_path: Path) -> list[Track]:
    with Store.open(tmp_path / "home" / "library.db") as store:
        return store.list_tracks()


FEATURED = Track(path_origin="/music/a.mp3", artist="Echo Unit", title="Storm (feat. Mira)")
URL = Track(path_origin="/music/b.mp3", artist="Bicep", title="Glue (freebeats.com)")


def test_dry_run(tmp_path: Path) -> None:
    library(tmp_path, FEATURED)

    result = invoke(tmp_path)

    assert result.exit_code == 0, result.stderr
    assert "title: 'Storm (feat. Mira)' → 'Storm'  (extract_featured)" in result.stdout
    assert "artist: 'Echo Unit' → 'Echo Unit feat. Mira'  (extract_featured)" in result.stdout
    assert tracks(tmp_path) == [FEATURED]


def test_only_some_fixes(tmp_path: Path) -> None:
    library(tmp_path, FEATURED, URL)

    result = invoke(tmp_path, "--only", "remove_urls", "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    by_path = {t.path: t for t in tracks(tmp_path)}
    assert by_path["/music/a.mp3"] == FEATURED
    assert by_path["/music/b.mp3"].title == "Glue"


def test_unknown_name(tmp_path: Path) -> None:
    library(tmp_path, URL)

    result = invoke(tmp_path, "--only", "remove_url")

    assert result.exit_code == 1
    assert "remove_url" in result.stderr


def test_rules_file_in_the_home(tmp_path: Path) -> None:
    library(tmp_path, FEATURED)
    (tmp_path / "home" / "rules.yaml").write_text("fixes: {extract_featured: false}\n")

    result = invoke(tmp_path, "--json")

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["tracks"] == []


def test_rules_option(tmp_path: Path) -> None:
    library(tmp_path, URL)
    rules = tmp_path / "mine.yaml"
    rules.write_text(
        "fixes: {remove_urls: false}\n"
        "rules: [{id: shout, then: {replace: title, pattern: Glue, with: GLUE}}]\n"
    )

    result = invoke(tmp_path, "--rules", str(rules), "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    assert tracks(tmp_path)[0].title == "GLUE (freebeats.com)"


def test_malformed_rules_file(tmp_path: Path) -> None:
    library(tmp_path, URL)
    rules = tmp_path / "bad.yaml"
    rules.write_text("rules: [{id: r, then: {set: titel, value: x}}]\n")

    result = invoke(tmp_path, "--rules", str(rules))

    assert result.exit_code == 1
    assert "rules[0] (r): unknown field 'titel'" in result.stderr


def test_only_repeated_or_with_commas(tmp_path: Path) -> None:
    library(tmp_path, FEATURED, URL)

    repeated = json.loads(
        invoke(tmp_path, "--only", "remove_urls", "--only", "extract_featured", "--json").stdout
    )
    commas = json.loads(invoke(tmp_path, "--only", "remove_urls,extract_featured", "--json").stdout)

    assert len(repeated["tracks"]) == len(commas["tracks"]) == 2


def test_under_a_folder(tmp_path: Path) -> None:
    new = tmp_path / "music" / "new"
    new.mkdir(parents=True)
    library(
        tmp_path,
        Track(path_origin=str(new / "a.mp3"), title="Glue (freebeats.com)"),
        Track(path_origin=str(tmp_path / "music" / "b.mp3"), title="Rise (freebeats.com)"),
    )

    document = json.loads(invoke(tmp_path, "--under", str(new), "--json").stdout)

    assert [t["path"] for t in document["tracks"]] == [normalize_path(str(new / "a.mp3"))]


def test_under_expands_the_home_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    new = tmp_path / "music" / "new"
    new.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    library(tmp_path, Track(path_origin=str(new / "a.mp3"), title="Glue (freebeats.com)"))

    result = invoke(tmp_path, "--under", "~/music/new", "--json")

    assert result.exit_code == 0, result.stderr
    assert len(json.loads(result.stdout)["tracks"]) == 1


def test_missing_folder_as_json(tmp_path: Path) -> None:
    library(tmp_path)

    result = invoke(tmp_path, "--under", str(tmp_path / "nowhere"), "--json")

    assert result.exit_code == 1
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "not_found"
    assert "nowhere" in error["message"]
