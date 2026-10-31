import shutil
from pathlib import Path

import pytest
from mutagen import id3
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.wave import WAVE

from support.audio import CLIPS
from tunedex.tagwrite.regions import LayoutError, audio_region, audio_sha256

SILENCE = {fmt: audio_sha256(CLIPS / f"silence.{fmt}", audio_region(CLIPS / f"silence.{fmt}"))
           for fmt in ("mp3", "flac", "wav", "aiff")}  # fmt: skip

TAGGED = [
    ("tagged-v24.mp3", "mp3"),
    ("tagged-v23-v1.mp3", "mp3"),
    ("tagged-ape.mp3", "mp3"),
    ("tagged.flac", "flac"),
    ("tagged.wav", "wav"),
    ("tagged.aiff", "aiff"),
]


@pytest.mark.parametrize(("name", "fmt"), TAGGED)
def test_the_audio_of_a_tagged_clip_is_the_silent_clip(name: str, fmt: str) -> None:
    path = CLIPS / name
    region = audio_region(path)
    assert audio_sha256(path, region) == SILENCE[fmt]
    assert region.tag_bytes == region.size - (region.end - region.start)


def test_untagged_mp3_is_all_audio() -> None:
    region = audio_region(CLIPS / "silence.mp3")
    assert (region.start, region.end) == (0, region.size)


def test_trailing_tags_are_outside_the_audio() -> None:
    plain = audio_region(CLIPS / "tagged-v24.mp3")
    trailed = audio_region(CLIPS / "tagged-ape.mp3")
    assert trailed.size - trailed.end == 128 + 128  # ID3v1, then the APEv2 tag with its header
    assert plain.end == plain.size


@pytest.mark.parametrize("name", ["silence.m4a", "silence.ogg", "tagged.m4a"])
def test_unsupported_formats_are_refused(name: str) -> None:
    with pytest.raises(LayoutError, match="not supported"):
        audio_region(CLIPS / name)


def test_junk_before_the_first_frame_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "junk.mp3"
    path.write_bytes(b"RIFF" + (CLIPS / "silence.mp3").read_bytes())
    with pytest.raises(LayoutError, match="MPEG"):
        audio_region(path)


def test_zero_padding_after_the_tag_is_tag_bytes(tmp_path: Path) -> None:
    clip = (CLIPS / "tagged-v24.mp3").read_bytes()
    start = audio_region(CLIPS / "tagged-v24.mp3").start
    path = tmp_path / "padded.mp3"
    path.write_bytes(clip[:start] + b"\x00" * 300 + clip[start:])
    region = audio_region(path)
    assert region.start == start + 300
    assert audio_sha256(path, region) == SILENCE["mp3"]


def test_damaged_files_are_refused(tmp_path: Path) -> None:
    flac = tmp_path / "cut.flac"
    flac.write_bytes((CLIPS / "tagged.flac").read_bytes()[:100])
    wav = tmp_path / "cut.wav"
    wav.write_bytes((CLIPS / "tagged.wav").read_bytes()[:30])
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    for path in (flac, wav, empty):
        with pytest.raises(LayoutError):
            audio_region(path)


def _retag(path: Path, fmt: str, text: str) -> None:
    if fmt == "flac":
        flac = FLAC(path)
        flac["TITLE"] = text
        flac.save()
        return
    if fmt == "mp3":
        tags = id3.ID3(path)
        tags.add(id3.TIT2(encoding=3, text=text))
        tags.save(path, v2_version=3, v1=1)
        return
    chunked = WAVE(path) if fmt == "wav" else AIFF(path)
    assert chunked.tags is not None
    chunked.tags.add(id3.TIT2(encoding=3, text=text))
    chunked.save(v2_version=3)


@pytest.mark.parametrize(("name", "fmt"), TAGGED)
@pytest.mark.parametrize("length", [1, 2_000, 70_000])
def test_the_audio_hash_survives_mutagen_rewriting_the_tags(
    tmp_path: Path, name: str, fmt: str, length: int
) -> None:
    path = tmp_path / name
    shutil.copyfile(CLIPS / name, path)
    _retag(path, fmt, "x" * length)  # smaller, larger than the padding, much larger
    region = audio_region(path)
    assert audio_sha256(path, region) == SILENCE[fmt]
    if length == 70_000 and fmt in ("mp3", "flac"):  # the leading tag grew: the audio moved
        assert region.start > audio_region(CLIPS / name).start
