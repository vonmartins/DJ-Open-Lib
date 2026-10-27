"""The scan, export and snapshot commands, run in-process (specs/cli)."""

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from djlib.cli import _flow, _home, app
from djlib.cli import snapshot as snapshot_cli
from djlib.model.playlist import Folder, Playlist
from djlib.model.track import Track
from djlib.store import Store
from support.audio import tagged_copy
from support.files import tree_bytes

runner = CliRunner()


def djlib(*args: str | Path, input: str | None = None) -> "Result":
    result = runner.invoke(app, [str(a) for a in args], input=input)
    return Result(result.exit_code, result.stdout, result.stderr)


class Result:
    def __init__(self, exit_code: int, stdout: str, stderr: str) -> None:
        self.exit_code, self.stdout, self.stderr = exit_code, stdout, stderr


@pytest.fixture
def music(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    tagged_copy(root, "mp3", name="a.mp3", title="A", artist="Artist")
    tagged_copy(root / "sub", "flac", name="b.flac", title="B")
    return root


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_flow, "stdin_is_interactive", lambda: True)
    monkeypatch.setattr(snapshot_cli, "stdin_is_interactive", lambda: True)


def library_with_playlists(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    a, b = (
        Track(path_origin="/music/a.mp3", title="A"),
        Track(path_origin="/music/b.mp3", title="B"),
    )
    with Store.open(home / "library.db") as store:
        store.add_track(a)
        store.add_track(b)
        store.add_node(Folder(name="Techno", children=(Playlist(name="Peak", entries=(a.id,)),)))
        store.add_node(Playlist(name="Warm", entries=(b.id,)))


def track_count(home: Path) -> int:
    with Store.open(home / "library.db") as store:
        return len(store.list_tracks())


# Home directory


def test_home_option(home: Path, music: Path) -> None:
    result = djlib("--home", home, "scan", music, "--apply", "--yes")

    assert result.exit_code == 0, result.stderr
    assert (home / "library.db").is_file()
    assert (home / "snapshots" / "library").is_dir()


def test_home_from_environment(home: Path, music: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJLIB_HOME", str(home))

    assert djlib("scan", music, "--apply", "--yes").exit_code == 0
    assert (home / "library.db").is_file()


def test_default_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert _home.default_home() == tmp_path / "xdg" / "djlib"
    monkeypatch.setenv("XDG_DATA_HOME", "relative/ignored")
    assert _home.default_home() == Path.home() / ".local" / "share" / "djlib"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _home.default_home() == Path.home() / "Library" / "Application Support" / "djlib"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert _home.default_home() == tmp_path / "local" / "djlib"


def test_dry_run_creates_nothing(home: Path, music: Path) -> None:
    result = djlib("--home", home, "scan", music)

    assert result.exit_code == 0
    assert "Tracks: 2 added" in result.stdout
    assert "Dry run: nothing was written" in result.stdout
    assert not home.exists()


# Dry run and confirmation


def test_plan_only(home: Path, music: Path) -> None:
    djlib("--home", home, "scan", music, "--apply", "--yes")
    tagged_copy(music, "ogg", name="c.ogg", title="C")
    database = (home / "library.db").read_bytes()

    result = djlib("--home", home, "scan", music)

    assert result.exit_code == 0
    assert "Tracks: 1 added" in result.stdout
    assert (home / "library.db").read_bytes() == database


def test_not_confirmed(home: Path, music: Path, interactive: None) -> None:
    result = djlib("--home", home, "scan", music, "--apply", input="n\n")

    assert result.exit_code == 0
    assert "Not applied." in result.stdout
    assert not home.exists()


def test_confirmed(home: Path, music: Path, interactive: None) -> None:
    result = djlib("--home", home, "scan", music, "--apply", input="y\n")

    assert result.exit_code == 0
    assert "Applied." in result.stdout
    assert track_count(home) == 2


def test_scripted(home: Path, music: Path) -> None:
    result = djlib("--home", home, "scan", music, "--apply", "--yes")

    assert result.exit_code == 0
    assert "Apply this plan?" not in result.stdout
    assert "Applied. Snapshot 000001-" in result.stdout


def test_apply_without_terminal_or_yes(home: Path, music: Path) -> None:
    result = djlib("--home", home, "scan", music, "--apply")

    assert result.exit_code == 1
    assert "pass --yes" in result.stderr
    assert not home.exists()


# Commands


def test_first_scan(home: Path, music: Path) -> None:
    djlib("--home", home, "scan", music, "--apply", "--yes")

    assert track_count(home) == 2


def test_missing_folder(home: Path, tmp_path: Path) -> None:
    result = djlib("--home", home, "scan", tmp_path / "nope")

    assert result.exit_code == 1
    assert result.stderr.startswith("error: ") and result.stderr.count("\n") == 1


def test_selected_playlist_exported(home: Path, tmp_path: Path) -> None:
    library_with_playlists(home)
    out = tmp_path / "out"

    result = djlib(
        "--home", home, "export", "m3u", out, "--playlist", "Techno/Peak", "--apply", "--yes"
    )

    assert result.exit_code == 0, result.stderr
    assert list(tree_bytes(out)) == ["Techno", "Techno/Peak.m3u8"]


def test_modified_export(home: Path, tmp_path: Path) -> None:
    library_with_playlists(home)
    out = tmp_path / "out"
    djlib("--home", home, "export", "m3u", out, "--apply", "--yes")

    result = djlib("--home", home, "export", "m3u", out, "--modified")

    assert result.exit_code == 0
    assert "Nothing to do." in result.stdout


def test_conflicting_options(home: Path, tmp_path: Path) -> None:
    library_with_playlists(home)

    result = djlib(
        "--home", home, "export", "m3u", tmp_path / "out", "--playlist", "A", "--modified"
    )

    assert result.exit_code != 0
    assert "cannot be combined" in result.stderr
    assert not (tmp_path / "out").exists()


def test_unknown_playlist(home: Path, tmp_path: Path) -> None:
    library_with_playlists(home)

    result = djlib("--home", home, "export", "m3u", tmp_path / "out", "--playlist", "Techno/Peek")

    assert result.exit_code == 1
    assert "did you mean 'Techno/Peak'" in result.stderr


def test_machine_readable_plan(home: Path, music: Path) -> None:
    result = djlib("--home", home, "scan", music, "--json")

    document = json.loads(result.stdout)
    assert (document["format"], document["version"]) == ("djlib-plan", 1)
    assert len(document["tracks"]) == 2
    assert document["result"] is None


def test_machine_readable_apply(home: Path, music: Path) -> None:
    result = djlib("--home", home, "scan", music, "--json", "--apply", "--yes")

    document = json.loads(result.stdout)
    assert document["result"]["status"] == "applied"


def test_stale_target(
    home: Path, tmp_path: Path, interactive: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    library_with_playlists(home)
    out = tmp_path / "out"
    djlib("--home", home, "export", "m3u", out, "--apply", "--yes")
    with Store.open(home / "library.db") as store:
        track = store.find_track_by_path("/music/b.mp3")
        assert track is not None
        store.update_track(type(track)(id=track.id, path_origin=track.path_origin, title="B2"))

    def edit_while_asking(as_json: bool) -> bool:
        (out / "Warm.m3u8").write_bytes(b"#EXTM3U\n# edited meanwhile\n")
        return True

    monkeypatch.setattr(_flow, "_ask", edit_while_asking)
    result = djlib("--home", home, "export", "m3u", out, "--apply")

    assert result.exit_code == 1
    assert result.stderr.count("\n") == 1
    assert "Warm.m3u8 changed since the plan was made" in result.stderr
    assert (out / "Warm.m3u8").read_bytes() == b"#EXTM3U\n# edited meanwhile\n"


def test_not_a_library(home: Path, music: Path) -> None:
    home.mkdir()
    (home / "library.db").write_text("not a database")

    result = djlib("--home", home, "scan", music)

    assert result.exit_code == 1
    assert "not an SQLite database" in result.stderr


# Snapshots


def test_snapshot_list(home: Path, music: Path) -> None:
    assert djlib("--home", home, "snapshot", "list").stdout == "No snapshots.\n"
    djlib("--home", home, "scan", music, "--apply", "--yes")

    text = djlib("--home", home, "snapshot", "list").stdout
    document = json.loads(djlib("--home", home, "snapshot", "list", "library", "--json").stdout)

    assert text.startswith("library  000001-")
    assert [s["target"] for s in document["snapshots"]] == ["library"]
    assert document["snapshots"][0]["reason"].startswith("scan ")


def test_restore_after_an_export(home: Path, tmp_path: Path) -> None:
    library_with_playlists(home)
    out = tmp_path / "out"
    out.mkdir()
    (out / "Warm.m3u8").write_bytes(b"#EXTM3U\n# mine\n")
    before = tree_bytes(out)
    export = json.loads(
        djlib("--home", home, "export", "m3u", out, "--json", "--apply", "--yes").stdout
    )
    assert tree_bytes(out) != before

    result = djlib(
        "--home",
        home,
        "snapshot",
        "restore",
        export["target"],
        export["result"]["snapshot"],
        "--yes",
    )

    assert result.exit_code == 0, result.stderr
    assert "holds the state from just before the restore" in result.stdout
    assert {k: v for k, v in tree_bytes(out).items() if v is not None} == {
        k: v for k, v in before.items() if v is not None
    }


def test_restore_needs_confirmation(home: Path, music: Path) -> None:
    djlib("--home", home, "scan", music, "--apply", "--yes")
    (snapshot_id,) = [
        s["id"]
        for s in json.loads(djlib("--home", home, "snapshot", "list", "--json").stdout)["snapshots"]
    ]

    result = djlib("--home", home, "snapshot", "restore", "library", snapshot_id)

    assert result.exit_code == 1
    assert "pass --yes" in result.stderr
    assert track_count(home) == 2


def test_restore_declined(home: Path, music: Path, interactive: None) -> None:
    djlib("--home", home, "scan", music, "--apply", "--yes")
    (snapshot_id,) = [
        s["id"]
        for s in json.loads(djlib("--home", home, "snapshot", "list", "--json").stdout)["snapshots"]
    ]

    result = djlib("--home", home, "snapshot", "restore", "library", snapshot_id, input="n\n")

    assert "Not restored." in result.stdout
    assert track_count(home) == 2


def test_restore_unknown_snapshot(home: Path) -> None:
    result = djlib(
        "--home", home, "snapshot", "restore", "library", "000009-20260101T000000Z", "--yes"
    )

    assert result.exit_code == 1
    assert "does not exist" in result.stderr
