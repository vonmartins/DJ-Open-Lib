import unicodedata

import pytest

from tunedex.model.errors import ValidationError
from tunedex.model.paths import normalize_path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (r"c:\Music\Artist\Track.mp3", "C:/Music/Artist/Track.mp3"),
        ("D:/Music/Track.mp3", "D:/Music/Track.mp3"),
        (r"C:\Music\\Sub\.\..\Track.mp3", "C:/Music/Track.mp3"),
        (r"\\server\share\Music\Track.mp3", "//server/share/Music/Track.mp3"),
        ("/music/Artist/Track.mp3", "/music/Artist/Track.mp3"),
        ("/music//a/./b/../Track.mp3", "/music/a/Track.mp3"),
        ("/music/Artist/", "/music/Artist"),
        ("/Volumes/USB/Music/Track.mp3", "/Volumes/USB/Music/Track.mp3"),
    ],
)
def test_normalizes(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


def test_backslash_is_a_filename_character_on_posix() -> None:
    assert normalize_path("/music/AC\\DC.mp3") == "/music/AC\\DC.mp3"


def test_unicode_forms_are_unified() -> None:
    nfd = unicodedata.normalize("NFD", "/music/Beyoncé.mp3")
    nfc = unicodedata.normalize("NFC", "/music/Beyoncé.mp3")

    assert nfd != nfc
    assert normalize_path(nfd) == normalize_path(nfc) == nfc


def test_case_is_preserved() -> None:
    assert normalize_path("/Music/Track.MP3") == "/Music/Track.MP3"


@pytest.mark.parametrize("raw", ["Music/Track.mp3", "./Track.mp3", "C:Track.mp3", "C:", ""])
def test_rejects_relative_or_empty(raw: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        normalize_path(raw)

    assert excinfo.value.field == "path"


def test_rejects_nul() -> None:
    with pytest.raises(ValidationError):
        normalize_path("/music/a\0b.mp3")


def test_error_names_the_caller_field() -> None:
    with pytest.raises(ValidationError) as excinfo:
        normalize_path("relative", entity="Playlist", field="location")

    assert (excinfo.value.entity, excinfo.value.field) == ("Playlist", "location")
