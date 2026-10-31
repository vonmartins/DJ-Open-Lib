from pathlib import Path

import pytest

from tunedex.adapters.m3u import M3UAdapter
from tunedex.adapters.m3u.reader import parse_text


@pytest.mark.parametrize("name", ["Warmup.M3U8", "set.m3u", "a.b.m3u8"])
def test_playlist_file_detected(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_text("#EXTM3U\n", encoding="utf-8")
    assert M3UAdapter().detect(tmp_path / name).matches


def test_other_file_not_detected(tmp_path: Path) -> None:
    (tmp_path / "a.mp3").write_bytes(b"")
    assert not M3UAdapter().detect(tmp_path / "a.mp3").matches


def test_directory_without_playlists(tmp_path: Path) -> None:
    (tmp_path / "a.mp3").write_bytes(b"")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "x.m3u8").write_text("", encoding="utf-8")

    detection = M3UAdapter().detect(tmp_path)

    assert not detection.matches
    assert detection.reason


def test_directory_with_nested_playlist(tmp_path: Path) -> None:
    (tmp_path / "Gigs").mkdir()
    (tmp_path / "Gigs" / "Set.m3u8").write_text("", encoding="utf-8")
    assert M3UAdapter().detect(tmp_path).matches


def test_missing_location(tmp_path: Path) -> None:
    detection = M3UAdapter().detect(tmp_path / "nothing")
    assert not detection.matches and "does not exist" in detection.reason


def test_artist_and_title() -> None:
    (entry,) = parse_text("#EXTM3U\n#EXTINF:372,Bicep - Glue\n/m/a.mp3\n").entries
    assert (entry.location, entry.duration_s, entry.display) == ("/m/a.mp3", 372.0, "Bicep - Glue")


def test_unknown_duration() -> None:
    (entry,) = parse_text("#EXTINF:-1,Intro\n/m/a.mp3").entries
    assert (entry.duration_s, entry.display) == (None, "Intro")


def test_float_duration_and_attributes() -> None:
    (entry,) = parse_text('#EXTINF:241.6 tvg-id="x",Caribou - Sun\n/m/a.mp3').entries
    assert (entry.duration_s, entry.display) == (241.6, "Caribou - Sun")


@pytest.mark.parametrize("text", ["#EXTM3U\r\n/a\r\n/b\r\n", "#EXTM3U\r/a\r/b", "/a\n\n  \n/b\n"])
def test_line_endings_and_blank_lines(text: str) -> None:
    assert [e.location for e in parse_text(text).entries] == ["/a", "/b"]


def test_extinf_applies_only_to_next_entry() -> None:
    first, second = parse_text("#EXTINF:10,One\n/a\n/b\n").entries
    assert (first.display, second.display) == ("One", None)


def test_directives_positions() -> None:
    parsed = parse_text("#EXTM3U\n#PLAYLIST:Mine\n/a\n#EXTVLCOPT:start-time=5\n/b\n# trailing\n")
    assert parsed.directives == [
        (0, "#PLAYLIST:Mine"),
        (1, "#EXTVLCOPT:start-time=5"),
        (2, "# trailing"),
    ]


def test_malformed_extinf_duration() -> None:
    (entry,) = parse_text("#EXTINF:abc,Title\n/a").entries
    assert (entry.duration_s, entry.display) == (None, "Title")
