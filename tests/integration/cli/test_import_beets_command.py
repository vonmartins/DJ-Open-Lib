"""``tunedex import beets`` (specs/cli)."""

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from support.beets import BeetsDatabase
from support.files import tree_bytes
from tunedex.cli import app
from tunedex.cli._beets import config_settings, default_beets_library, default_music_dir
from tunedex.model.paths import normalize_path
from tunedex.store import Store

runner = CliRunner()


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("BEETSDIR", "XDG_CONFIG_HOME", "APPDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "user")
    monkeypatch.setenv("HOME", str(tmp_path / "user"))  # what ~ expands to
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.setattr(sys, "platform", "linux")
    return tmp_path / "user"


def invoke(tmp_path: Path, *arguments: str) -> Result:
    return runner.invoke(app, ["--home", str(tmp_path / "home"), "import", "beets", *arguments])


def titles(tmp_path: Path) -> list[str | None]:
    with Store.open(tmp_path / "home" / "library.db") as store:
        return sorted(t.title for t in store.list_tracks())  # type: ignore[type-var]


def test_import_from_a_path(tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "music" / ".beetslibrary.db")
    beets.add_item("/music/a.mp3", title="A")
    before = tree_bytes(tmp_path / "music")

    result = invoke(tmp_path, str(beets.path), "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    assert titles(tmp_path) == ["A"]
    assert tree_bytes(tmp_path / "music") == before


def test_library_setting(tmp_path: Path, home: Path) -> None:
    config = home / ".config" / "beets"
    config.mkdir(parents=True)
    (config / "config.yaml").write_text(
        "directory: ~/Music\nlibrary: '~/Music/.beets.db'  # mine\nimport:\n  library: no\n"
    )
    beets = BeetsDatabase(home / "Music" / ".beets.db")
    beets.add_item("/music/a.mp3", title="A")

    assert default_beets_library() == home / "Music" / ".beets.db"
    result = invoke(tmp_path, "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    assert titles(tmp_path) == ["A"]


def test_beetsdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEETSDIR", str(tmp_path / "beetsdir"))
    BeetsDatabase(tmp_path / "beetsdir" / "library.db").add_item("/music/a.mp3", title="A")

    result = invoke(tmp_path, "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    assert titles(tmp_path) == ["A"]


def test_music_directory_option(tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "library.db", schema="2.14")
    beets.add_item("Techno/a.mp3", title="A")
    music = tmp_path / "mnt" / "music"

    result = invoke(tmp_path, str(beets.path), "--music-dir", str(music), "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    with Store.open(tmp_path / "home" / "library.db") as store:
        (track,) = store.list_tracks()
    assert track.path == normalize_path(str(music / "Techno" / "a.mp3"))


def test_directory_setting(home: Path) -> None:
    config = home / ".config" / "beets"
    config.mkdir(parents=True)
    music = home / "srv" / "music"
    (config / "config.yaml").write_text(f'directory: "{music}"\n')

    assert config_settings(config) == {"directory": str(music)}
    assert default_music_dir() == music


def test_defaults_without_config(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert default_beets_library() == home / ".config" / "beets" / "library.db"
    assert default_music_dir() == home / "Music"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(home / "AppData"))
    assert default_beets_library() == home / "AppData" / "beets" / "library.db"


def test_no_beets_library_found(tmp_path: Path, home: Path) -> None:
    result = invoke(tmp_path)

    assert result.exit_code == 1
    assert f"no beets library at {home / '.config' / 'beets' / 'library.db'}" in result.stderr


def test_import_with_a_search_folder(tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "library.db")
    beets.add_item("/mnt/server/Calyx/a.mp3", title="A")
    beets.add_item("/mnt/server/Phace/b.mp3", title="B")
    artists = tmp_path / "Artists"
    (artists / "Calyx").mkdir(parents=True)
    (artists / "Calyx" / "a.mp3").write_bytes(b"x")

    result = invoke(tmp_path, str(beets.path), "--find-in", str(artists), "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    assert titles(tmp_path) == ["A"]


def test_search_folder_missing(tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "library.db")

    result = invoke(tmp_path, str(beets.path), "--find-in", str(tmp_path / "nowhere"))

    assert result.exit_code == 1
    assert "nowhere does not exist" in result.stderr
