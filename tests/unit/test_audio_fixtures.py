from pathlib import Path

import mutagen
import pytest

from support.audio import CLIPS, FORMATS, tagged_copy


@pytest.mark.parametrize("fmt", FORMATS)
def test_clip_is_small_and_untagged(fmt: str) -> None:
    clip = CLIPS / f"silence.{fmt}"
    audio = mutagen.File(clip)

    assert clip.stat().st_size < 16_000
    assert audio is not None
    assert not audio.tags


@pytest.mark.parametrize("fmt", FORMATS)
def test_helper_writes_a_title(tmp_path: Path, fmt: str) -> None:
    path = tagged_copy(tmp_path, fmt, title="Glue")
    audio = mutagen.File(path)

    assert audio is not None and audio.tags
    assert "Glue" in str(audio.tags)
    assert (CLIPS / f"silence.{fmt}").stat().st_size < 16_000
