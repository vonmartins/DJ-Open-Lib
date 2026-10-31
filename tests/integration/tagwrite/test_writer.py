import os
import shutil
from pathlib import Path

import pytest
from mutagen import id3
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.wave import WAVE

from support.audio import CLIPS, tagged_copy
from tunedex.model.key import Key, Mode
from tunedex.sources.tags import read_file
from tunedex.tagwrite.regions import audio_region, audio_sha256
from tunedex.tagwrite.writer import TagWriteError, text_of, write_tags


def _copy(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    shutil.copyfile(CLIPS / name, path)
    return path


def _audio(path: Path) -> str:
    return audio_sha256(path, audio_region(path))


@pytest.mark.parametrize(
    "name", ["tagged-v24.mp3", "tagged-v23-v1.mp3", "tagged-ape.mp3", "tagged.wav", "tagged.aiff"]
)
def test_art_and_ids_are_kept(tmp_path: Path, name: str) -> None:
    path = _copy(tmp_path, name)
    before = (
        MP3(path).tags
        if name.endswith(".mp3")
        else (WAVE if name.endswith("wav") else AIFF)(path).tags
    )
    assert before is not None
    audio = _audio(path)

    write_tags(path, {"title": "Galaxy"})

    after = (
        MP3(path).tags
        if name.endswith(".mp3")
        else (WAVE if name.endswith("wav") else AIFF)(path).tags
    )
    assert after is not None
    assert str(after["TIT2"]) == "Galaxy"
    assert after.version == (2, 3, 0)
    assert after["APIC:"].data == before["APIC:"].data
    assert after["UFID:http://musicbrainz.org"].data == before["UFID:http://musicbrainz.org"].data
    assert str(after["TXXX:MusicBrainz Release Track Id"]) == str(
        before["TXXX:MusicBrainz Release Track Id"]
    )
    assert str(after["COMM:iTunNORM:eng"]) == str(before["COMM:iTunNORM:eng"])
    assert str(after["TPE1"]) == "Sam Paganini"
    assert _audio(path) == audio


def test_flac_picture_and_ids_are_kept(tmp_path: Path) -> None:
    path = _copy(tmp_path, "tagged.flac")
    audio = _audio(path)
    write_tags(path, {"title": "Galaxy", "artist": None})
    flac = FLAC(path)
    assert flac["TITLE"] == ["Galaxy"]
    assert "ARTIST" not in flac
    assert flac["MUSICBRAINZ_TRACKID"] == ["6340a9b8-f427-4d89-a842-971a52ad3ce4"]
    assert len(flac.pictures) == 1
    assert _audio(path) == audio


def test_version_24_becomes_23(tmp_path: Path) -> None:
    path = _copy(tmp_path, "tagged-v24.mp3")
    write_tags(path, {"artist": "Paganini"})
    tags = id3.ID3(path, translate=False)
    assert tags.version == (2, 3, 0)
    assert str(tags["TPE1"]) == "Paganini"
    assert str(tags["TYER"]) == "2012"  # converted, with the rest of the date
    assert "TSOP" not in tags  # ID3v2.3 cannot hold it
    assert read_file(path).values["year"] == 2012


def test_id3v1_is_updated_when_present(tmp_path: Path) -> None:
    path = _copy(tmp_path, "tagged-v23-v1.mp3")
    write_tags(path, {"title": "Galaxy"})
    assert path.read_bytes()[-128:][:3] == b"TAG"
    assert path.read_bytes()[-125:-95].rstrip(b"\x00") == b"Galaxy"


def test_id3v1_is_not_added(tmp_path: Path) -> None:
    path = _copy(tmp_path, "tagged-v24.mp3")
    write_tags(path, {"title": "Galaxy"})
    assert path.read_bytes()[-128:][:3] != b"TAG"


def test_untagged_files_get_tags(tmp_path: Path) -> None:
    for fmt in ("mp3", "flac", "wav", "aiff"):
        path = tagged_copy(tmp_path, fmt)
        audio = _audio(path)
        write_tags(path, {"title": "Glue", "bpm": "127"})
        values = read_file(path).values
        assert (values["title"], values["bpm"]) == ("Glue", 127.0), fmt
        assert _audio(path) == audio


def test_numbers_keep_their_total(tmp_path: Path) -> None:
    mp3 = _copy(tmp_path, "tagged-v24.mp3")
    write_tags(mp3, {"track_number": "4", "disc_number": "1"})
    tags = id3.ID3(mp3)
    assert (str(tags["TRCK"]), str(tags["TPOS"])) == ("4/12", "1")
    flac = _copy(tmp_path, "tagged.flac")
    write_tags(flac, {"track_number": "4"})
    assert FLAC(flac)["TRACKNUMBER"] == ["4/12"]


def test_field_removal(tmp_path: Path) -> None:
    path = tagged_copy(tmp_path, "mp3", title="Glue", grouping="Peak", comment="Great closer")
    tags = id3.ID3(path)
    tags.add(id3.GRP1(encoding=3, text="Peak"))
    tags.save(path)
    write_tags(path, {"grouping": None, "comment": None, "album": None})
    tags = id3.ID3(path)
    assert "TIT1" not in tags and "GRP1" not in tags
    assert not tags.getall("COMM")
    assert read_file(path).values["title"] == "Glue"


def test_comment_keeps_itunes_data(tmp_path: Path) -> None:
    path = _copy(tmp_path, "tagged-v24.mp3")
    write_tags(path, {"comment": "Warm-up"})
    tags = id3.ID3(path)
    assert [str(f) for f in tags.getall("COMM") if f.desc == ""] == ["Warm-up"]
    assert "COMM:iTunNORM:eng" in tags
    assert read_file(path).values["comment"] == "Warm-up"


def test_written_values_read_back(tmp_path: Path) -> None:
    for fmt in ("mp3", "flac", "wav", "aiff"):
        path = tagged_copy(tmp_path, fmt)
        write_tags(
            path,
            {"title": "Glue", "year": "2017", "key": "Am", "bpm": "127.5", "label": "Ninja Tune",
             "remixer": "Scuba", "lyricist": "Nobody", "grouping": "Peak", "comment": "Closer"},
        )  # fmt: skip
        values = read_file(path).values
        assert values["year"] == 2017, fmt
        assert values["key"] == Key(tonic=9, mode=Mode.MINOR), fmt
        assert values["bpm"] == 127.5, fmt
        assert (values["label"], values["remixer"], values["lyricist"]) == (
            "Ninja Tune", "Scuba", "Nobody"
        ), fmt  # fmt: skip
        assert (values["grouping"], values["comment"]) == ("Peak", "Closer"), fmt


def test_text_formats() -> None:
    a_minor = Key(tonic=9, mode=Mode.MINOR)
    assert text_of("key", a_minor) == "Am"
    assert text_of("key", a_minor, key_original="1m") == "1m"
    assert text_of("key", a_minor, key_original="Cm") == "Am"
    assert text_of("key", Key(tonic=6, mode=Mode.MAJOR)) == "F#"
    assert text_of("bpm", 128.0) == "128"
    assert text_of("bpm", 127.456) == "127.46"
    assert text_of("track_number", 3) == "3"
    assert text_of("title", "") is None
    assert text_of("title", None) is None


def test_unsupported_formats_are_not_written(tmp_path: Path) -> None:
    path = tagged_copy(tmp_path, "m4a")
    with pytest.raises(TagWriteError, match="not written"):
        write_tags(path, {"title": "Glue"})


def test_a_failed_write_leaves_the_file_and_no_temporary(tmp_path: Path) -> None:
    path = tmp_path / "junk.mp3"
    path.write_bytes(b"RIFF" + (CLIPS / "silence.mp3").read_bytes())
    before = path.read_bytes()
    with pytest.raises(TagWriteError):
        write_tags(path, {"title": "Glue"})
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["junk.mp3"]


def test_the_written_file_keeps_its_permissions(tmp_path: Path) -> None:
    path = _copy(tmp_path, "tagged-v24.mp3")
    path.chmod(0o640)
    write_tags(path, {"title": "Galaxy"})
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o640
