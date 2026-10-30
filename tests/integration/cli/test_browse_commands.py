"""``djlib status``, ``list``, ``show`` and ``playlists`` (specs/cli, library-query)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from djlib.cli import app
from djlib.model.cue import Cue, CueKind
from djlib.model.playlist import Folder, Playlist
from djlib.model.track import Track
from djlib.store import Store

runner = CliRunner()


def invoke(tmp_path: Path, *arguments: str) -> Result:
    return runner.invoke(app, ["--home", str(tmp_path / "home"), *arguments])


@pytest.fixture
def music(tmp_path: Path) -> Path:
    """Three tracks with files, in a library with a folder of two playlists."""
    root = tmp_path / "music"
    (root / "techno").mkdir(parents=True)
    (root / "house").mkdir()
    tracks = []
    for name, fields in (
        ("techno/a.mp3", {"artist": "Velk", "title": "Rise", "genre": "Techno", "bpm": 132.0}),
        ("techno/b.mp3", {"artist": "Arno", "title": "Fall", "genre": "Techno", "bpm": 128.0}),
        ("house/c.mp3", {"artist": "Arno", "title": "Glow", "genre": "House", "bpm": 124.0}),
    ):
        (root / name).write_bytes(b"audio")
        tracks.append(Track(path_origin=str(root / name), **fields))  # pyright: ignore[reportArgumentType]
    a, b, c = tracks
    (tmp_path / "home").mkdir()
    with Store.open(tmp_path / "home" / "library.db") as store:
        for track in tracks:
            store.add_track(track)
        store.update_track(
            Track(
                path_origin=a.path_origin,
                id=a.id,
                artist="Velk",
                title="Rise",
                genre="Techno",
                bpm=132.0,
                cues=(Cue(kind=CueKind.HOT, start_us=32_000_000, slot=0, name="drop"),),
            )
        )
        sets = Folder(
            name="Sets",
            children=(
                Playlist(name="Friday", entries=(a.id, b.id)),
                Playlist(name="Saturday", entries=(c.id,)),
            ),
        )
        store.add_node(sets)
    return root


def test_status(tmp_path: Path, music: Path) -> None:
    (music / "house" / "c.mp3").unlink()

    result = invoke(tmp_path, "status")

    assert result.exit_code == 0, result.stderr
    assert "Tracks: 3 (1 missing on this computer)" in result.stdout
    assert "Playlists: 2, smartlists: 0, folders: 1" in result.stdout
    document = json.loads(invoke(tmp_path, "status", "--json").stdout)
    assert (document["format"], document["tracks"], document["missing"]) == (
        "djlib-status",
        3,
        1,
    )


def test_status_of_a_new_home(tmp_path: Path) -> None:
    result = invoke(tmp_path, "status")

    assert result.exit_code == 0, result.stderr
    assert "Tracks: 0" in result.stdout
    assert not (tmp_path / "home").exists()


def test_list_filtered(tmp_path: Path, music: Path) -> None:
    result = invoke(tmp_path, "list", "--where", "genre=techno", "--where", "bpm>130")

    assert result.exit_code == 0, result.stderr
    assert "Rise" in result.stdout
    assert "Fall" not in result.stdout
    assert result.stdout.endswith("1 track\n")


def test_list_ordered_and_as_json(tmp_path: Path, music: Path) -> None:
    document = json.loads(invoke(tmp_path, "list", "--json").stdout)

    assert (document["format"], document["version"]) == ("djlib-tracks", 1)
    assert [t["title"] for t in document["tracks"]] == ["Fall", "Glow", "Rise"]
    assert document["tracks"][0]["bpm"] == 128.0


def test_list_by_playlist_folder_and_under(tmp_path: Path, music: Path) -> None:
    by_folder = json.loads(invoke(tmp_path, "list", "-p", "Sets", "--json").stdout)
    by_playlist = json.loads(invoke(tmp_path, "list", "-p", "Sets/Friday", "--json").stdout)
    under = json.loads(invoke(tmp_path, "list", "--under", str(music / "house"), "--json").stdout)

    assert len(by_folder["tracks"]) == 3
    assert [t["title"] for t in by_playlist["tracks"]] == ["Fall", "Rise"]
    assert [t["title"] for t in under["tracks"]] == ["Glow"]


def test_list_missing(tmp_path: Path, music: Path) -> None:
    (music / "techno" / "b.mp3").unlink()

    document = json.loads(invoke(tmp_path, "list", "--missing", "--json").stdout)

    assert [t["title"] for t in document["tracks"]] == ["Fall"]


@pytest.mark.parametrize(
    ("arguments", "code"),
    [(["--where", "bpm>fast"], "invalid_rule"), (["-p", "Nope"], "unknown_playlist")],
)
def test_list_errors(tmp_path: Path, music: Path, arguments: list[str], code: str) -> None:
    text = invoke(tmp_path, "list", *arguments)
    as_json = invoke(tmp_path, "list", *arguments, "--json")

    assert text.exit_code == as_json.exit_code == 1
    assert arguments[1] in text.stderr
    assert json.loads(as_json.stderr)["error"]["code"] == code


def test_show_by_relative_path(
    tmp_path: Path, music: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(music / "techno")

    result = invoke(tmp_path, "show", "a.mp3")

    assert result.exit_code == 0, result.stderr
    assert result.stdout.startswith("Velk - Rise\n")
    assert "genre          Techno" in result.stdout
    assert "hot 1  0:32        drop" in result.stdout
    assert "Playlists: Sets/Friday" in result.stdout


def test_show_as_json_by_id(tmp_path: Path, music: Path) -> None:
    listed = json.loads(invoke(tmp_path, "list", "--json").stdout)["tracks"][0]

    document = json.loads(invoke(tmp_path, "show", listed["id"], "--json").stdout)

    assert document["format"] == "djlib-track"
    assert document["track"]["title"] == "Fall"
    assert (document["present"], document["playlists"]) == (True, ["Sets/Friday"])


def test_show_unknown_track(tmp_path: Path, music: Path) -> None:
    result = invoke(tmp_path, "show", str(music / "none.mp3"))

    assert result.exit_code == 1
    assert "none.mp3" in result.stderr


def test_playlists(tmp_path: Path, music: Path) -> None:
    result = invoke(tmp_path, "playlists")

    assert result.exit_code == 0, result.stderr
    assert result.stdout == "Sets/\n  Friday  (2 tracks)\n  Saturday  (1 track)\n"
    document = json.loads(invoke(tmp_path, "playlists", "--json").stdout)
    assert [(n["path"], n["tracks"]) for n in document["nodes"]] == [
        ("Sets", None),
        ("Sets/Friday", 2),
        ("Sets/Saturday", 1),
    ]


def test_read_only_commands_change_nothing(tmp_path: Path, music: Path) -> None:
    database = tmp_path / "home" / "library.db"
    before = database.read_bytes()

    for command in (["status"], ["list"], ["playlists"], ["show", str(music / "house/c.mp3")]):
        assert invoke(tmp_path, *command).exit_code == 0

    assert database.read_bytes() == before
    assert not (tmp_path / "home" / "snapshots").exists()


def test_status_lists_snapshots_in_columns(tmp_path: Path, music: Path) -> None:
    invoke(tmp_path, "scan", str(music), "--apply", "--yes")

    lines = invoke(tmp_path, "status").stdout.splitlines()

    row = lines[lines.index("Last snapshots:") + 1]
    assert row.startswith("  library  000001-")
    assert row.endswith(f"scan {music}")


def test_same_bpm_in_list_and_show(tmp_path: Path, music: Path) -> None:
    listed = invoke(tmp_path, "list", "--where", "title=Fall").stdout
    shown = invoke(tmp_path, "show", str(music / "techno" / "b.mp3")).stdout

    assert "  128  " in listed
    assert "128.0" not in listed
    assert "  bpm            128\n" in shown
