from pathlib import Path

import pytest
from mutagen.flac import FLAC

from support.audio import FORMATS, tagged_copy, write_tags
from tunedex.model.key import Key, Mode
from tunedex.sources.tags import read_file

ALL_TAGS = {
    "title": "Glue",
    "artist": "Bicep",
    "album": "Bicep",
    "album_artist": "Bicep",
    "genre": "Electronic",
    "date": "2017-09-01",
    "track": "3/12",
    "disc": "1/2",
    "bpm": "127",
    "key": "Am",
    "composer": "Andy Ferguson",
    "remixer": "Someone",
    "label": "Ninja Tune",
    "comment": "Great closer",
    "grouping": "Peak",
    "lyricist": "Nobody",
}


def test_mp3_tags_read(tmp_path: Path) -> None:
    path = tagged_copy(
        tmp_path,
        "mp3",
        title="Glue",
        artist="Bicep",
        date="2017",
        track="3/12",
        bpm="127",
        key="Am",
    )

    values = read_file(path).values

    assert values["title"] == "Glue"
    assert values["artist"] == "Bicep"
    assert values["year"] == 2017
    assert values["track_number"] == 3
    assert values["bpm"] == 127.0
    assert values["key_original"] == "Am"
    assert values["key"] == Key(tonic=9, mode=Mode.MINOR)


@pytest.mark.parametrize("fmt", FORMATS)
def test_same_fields_across_formats(tmp_path: Path, fmt: str) -> None:
    path = tagged_copy(tmp_path, fmt, **ALL_TAGS)

    result = read_file(path)

    assert result.warnings == []
    values = result.values
    assert {k: values.get(k) for k in ("title", "artist", "album", "album_artist", "genre")} == {
        "title": "Glue",
        "artist": "Bicep",
        "album": "Bicep",
        "album_artist": "Bicep",
        "genre": "Electronic",
    }
    assert (values["year"], values["track_number"], values["disc_number"], values["bpm"]) == (
        2017,
        3,
        1,
        127.0,
    )
    assert (values["key_original"], values["key"]) == ("Am", Key(tonic=9, mode=Mode.MINOR))
    assert (values["composer"], values["remixer"], values["label"]) == (
        "Andy Ferguson",
        "Someone",
        "Ninja Tune",
    )
    assert (values["comment"], values["grouping"], values["lyricist"]) == (
        "Great closer",
        "Peak",
        "Nobody",
    )
    expected_format = {
        "mp3": "mp3",
        "flac": "flac",
        "wav": "wav",
        "aiff": "aiff",
        "m4a": "m4a",
        "ogg": "ogg",
    }[fmt]
    assert values["file_format"] == expected_format
    assert values["sample_rate"] == 8000
    assert 400_000 < values["duration_us"] < 800_000


@pytest.mark.parametrize("fmt", FORMATS)
def test_untagged_clip_has_only_properties(tmp_path: Path, fmt: str) -> None:
    values = read_file(tagged_copy(tmp_path, fmt)).values
    assert set(values) <= {"file_format", "duration_us", "bitrate", "sample_rate"}


def test_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.mp3"
    path.write_bytes(b"definitely not audio" * 10)

    result = read_file(path)

    assert result.values == {"file_format": "mp3"}
    assert len(result.warnings) == 1 and "broken.mp3" in result.warnings[0]


def test_multiple_values_joined(tmp_path: Path) -> None:
    path = tagged_copy(tmp_path, "flac")
    audio = FLAC(path)
    audio["ARTIST"] = ["Bicep", "Clara La San"]
    audio.save()

    assert read_file(path).values["artist"] == "Bicep; Clara La San"


@pytest.mark.parametrize(("bpm", "expected"), [("127.5", 127.5), ("128,0", 128.0)])
def test_bpm_parsing(tmp_path: Path, bpm: str, expected: float) -> None:
    assert read_file(tagged_copy(tmp_path, "mp3", bpm=bpm)).values["bpm"] == expected


def test_invalid_values_dropped_with_warning(tmp_path: Path) -> None:
    path = tagged_copy(tmp_path, "ogg", bpm="fast", track="A1")

    result = read_file(path)

    assert "bpm" not in result.values and "track_number" not in result.values
    assert len(result.warnings) == 2


@pytest.mark.parametrize("fmt", ["mp3", "flac", "m4a"])
def test_zero_values_read_as_absent(tmp_path: Path, fmt: str) -> None:
    path = tagged_copy(tmp_path, fmt, track="0", disc="0", date="0000", bpm="0")

    result = read_file(path)

    assert {"track_number", "disc_number", "year", "bpm"}.isdisjoint(result.values)
    assert result.warnings == []


def test_open_key_and_unknown_key(tmp_path: Path) -> None:
    open_key = read_file(tagged_copy(tmp_path, "mp3", name="a.mp3", key="4m")).values
    unknown = read_file(tagged_copy(tmp_path, "mp3", name="b.mp3", key="8A")).values

    assert open_key["key"] == Key(tonic=6, mode=Mode.MINOR)
    assert (unknown["key_original"], unknown["key"]) == ("8A", None)


def test_rewritten_tags_are_read(tmp_path: Path) -> None:
    path = tagged_copy(tmp_path, "m4a", title="Old")
    write_tags(path, title="New")
    assert read_file(path).values["title"] == "New"
