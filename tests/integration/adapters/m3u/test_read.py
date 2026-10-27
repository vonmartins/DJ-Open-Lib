from pathlib import Path

import pytest

from djlib.adapters.contract import ReadOptions
from djlib.adapters.errors import AdapterReadError
from djlib.adapters.m3u import M3UAdapter
from djlib.adapters.pathmap import PathMapping, PathRule
from djlib.model.library import Library
from djlib.model.paths import normalize_path
from djlib.model.playlist import Folder, Playlist
from support.adapter_contract import assert_read_only

FIXTURES = Path(__file__).parents[3] / "fixtures" / "m3u"
TREE = FIXTURES / "tree"
SINGLE = FIXTURES / "single"


def paths(library: Library, playlist: Playlist) -> list[str]:
    return [library.tracks[e].path for e in playlist.entries]


def test_read_playlist_file(tmp_path: Path) -> None:
    file = tmp_path / "Set.m3u8"
    file.write_text("/m/a.mp3\n/m/b.mp3\n/m/a.mp3\n", encoding="utf-8")

    library = assert_read_only(M3UAdapter(), file).library

    (playlist,) = library.playlists
    assert isinstance(playlist, Playlist)
    assert playlist.name == "Set"
    assert paths(library, playlist) == ["/m/a.mp3", "/m/b.mp3", "/m/a.mp3"]
    assert len(library.tracks) == 2


def test_read_directory_tree() -> None:
    library = assert_read_only(M3UAdapter(), TREE).library

    gigs, peak = library.playlists
    assert isinstance(gigs, Folder) and gigs.name == "Gigs"
    (year,) = gigs.children
    assert isinstance(year, Folder) and year.name == "2026"
    (warmup,) = year.children
    assert isinstance(warmup, Playlist) and warmup.name == "Warmup"
    assert isinstance(peak, Playlist) and peak.name == "Peak"
    assert all(n.name not in {"Secret", "Empty", ".hidden", "notes"} for _, _, n in library.walk())


def test_shared_track_and_extinf() -> None:
    library = M3UAdapter().read(TREE).library
    (gigs, peak) = library.playlists
    warmup = gigs.children[0].children[0]  # pyright: ignore[reportAttributeAccessIssue]
    assert isinstance(peak, Playlist) and isinstance(warmup, Playlist)

    assert peak.entries[0] == warmup.entries[1] == peak.entries[2]
    glue = library.tracks[peak.entries[0]]
    assert (glue.artist, glue.title, glue.duration_us) == ("Bicep", "Glue", 372_000_000)
    intro = library.tracks[peak.entries[1]]
    assert (intro.artist, intro.title, intro.duration_us) == (None, "Intro", None)


def test_relative_entry_resolved_against_playlist_dir() -> None:
    library = M3UAdapter().read(TREE / "Gigs" / "2026" / "Warmup.m3u8").library
    (warmup,) = library.playlists
    assert isinstance(warmup, Playlist)

    expected = normalize_path(str((FIXTURES.parent / "music" / "Warm.mp3").absolute()))
    assert paths(library, warmup)[0] == expected


def test_mixed_file_uri_stream_and_directive() -> None:
    result = assert_read_only(M3UAdapter(), SINGLE / "mixed.m3u8")
    (playlist,) = result.library.playlists
    assert isinstance(playlist, Playlist)

    assert paths(result.library, playlist) == ["/music/Beyoncé.mp3", "/music/b.mp3"]
    first = result.library.tracks[playlist.entries[0]]
    assert (first.artist, first.title, first.duration_us) == ("Caribou", "Sun", 241_600_000)
    assert any("http://radio.example/stream" in w for w in result.warnings)
    assert playlist.unmapped == {
        "m3u": {
            "directives": [
                {"before": 1, "track": str(playlist.entries[1]), "line": "#EXTVLCOPT:start-time=5"}
            ]
        }
    }


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("file:///C:/Music/a%20b.mp3", "C:/Music/a b.mp3"),
        ("file://server/share/a.mp3", "//server/share/a.mp3"),
        ("file://localhost/music/a.mp3", "/music/a.mp3"),
        (r"D:\Music\a.mp3", "D:/Music/a.mp3"),
        (r"\\nas\music\a.mp3", "//nas/music/a.mp3"),
    ],
)
def test_entry_forms(tmp_path: Path, entry: str, expected: str) -> None:
    file = tmp_path / "x.m3u8"
    file.write_text(entry + "\n", encoding="utf-8")
    library = M3UAdapter().read(file).library
    assert [t.path for t in library.tracks.values()] == [expected]


def test_path_mapping_on_read(tmp_path: Path) -> None:
    file = tmp_path / "x.m3u8"
    file.write_text("D:\\Music\\House\\a.mp3\n", encoding="utf-8")
    options = ReadOptions(path_mapping=PathMapping((PathRule("/mnt/music", "D:/Music"),)))

    library = M3UAdapter().read(file, options).library

    assert [t.path for t in library.tracks.values()] == ["/mnt/music/House/a.mp3"]


def test_every_fixture_is_read_only() -> None:
    for location in (TREE, SINGLE / "mixed.m3u8", SINGLE / "legacy.m3u"):
        assert_read_only(M3UAdapter(), location)


# Text encoding


def test_legacy_encoding() -> None:
    result = M3UAdapter().read(SINGLE / "legacy.m3u")

    (track,) = result.library.tracks.values()
    assert (track.path, track.artist, track.title) == ("/music/café.mp3", "Café del Mar", "Café")
    assert any("legacy.m3u" in w and "Windows-1252" in w for w in result.warnings)


def test_invalid_utf8_in_m3u8() -> None:
    with pytest.raises(AdapterReadError, match=r"broken\.m3u8"):
        M3UAdapter().read(SINGLE / "broken.m3u8")


def test_byte_order_mark_ignored(tmp_path: Path) -> None:
    file = tmp_path / "bom.m3u8"
    file.write_bytes(b"\xef\xbb\xbf/m/a.mp3\n")
    assert [t.path for t in M3UAdapter().read(file).library.tracks.values()] == ["/m/a.mp3"]
