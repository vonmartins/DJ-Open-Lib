import os
import sys
from pathlib import Path

import pytest

from support.audio import FORMATS, tagged_copy
from tunedex.sources.folder_scan import discover, quick_hash


def found_names(root: Path) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    names = [str(f.path.relative_to(root)).replace("\\", "/") for f in discover(root, warnings)]
    return names, warnings


def test_supported_formats_found(tmp_path: Path) -> None:
    for index, fmt in enumerate(FORMATS):
        tagged_copy(tmp_path / f"dir{index % 2}" / "sub", fmt, name=f"t{index}.{fmt}")
    tagged_copy(tmp_path, "mp3", name="Upper.MP3")
    tagged_copy(tmp_path, "aiff", name="short.aif")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    tagged_copy(tmp_path, "mp3", name="._Track.mp3")
    tagged_copy(tmp_path / ".hidden", "mp3")

    names, warnings = found_names(tmp_path)

    assert warnings == []
    assert sorted(names) == sorted(
        [f"dir{i % 2}/sub/t{i}.{fmt}" for i, fmt in enumerate(FORMATS)] + ["Upper.MP3", "short.aif"]
    )


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_directory_symlinks_not_followed(tmp_path: Path) -> None:
    tagged_copy(tmp_path / "real", "mp3")
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)

    names, _ = found_names(tmp_path)

    assert names == ["real/track.mp3"]


@pytest.mark.skipif(sys.platform != "linux", reason="only Linux allows non-UTF-8 file names")
def test_non_utf8_name_skipped(tmp_path: Path) -> None:
    good = tagged_copy(tmp_path, "mp3", name="good.mp3")
    bad = Path(os.fsdecode(os.fsencode(tmp_path) + b"/bad\xff.mp3"))
    bad.write_bytes(good.read_bytes())

    names, warnings = found_names(tmp_path)

    assert names == ["good.mp3"]
    assert len(warnings) == 1 and "bad\\xff.mp3" in warnings[0]


def test_quick_hash_small_and_large_files(tmp_path: Path) -> None:
    small = tmp_path / "small"
    small.write_bytes(b"a" * 100)
    large = tmp_path / "large"
    large.write_bytes(b"h" * 20_000 + b"middle" + b"t" * 20_000)
    same_edges = tmp_path / "same_edges"
    same_edges.write_bytes(b"h" * 20_000 + b"MIDDLE" + b"t" * 20_000)

    assert quick_hash(small, 100) != quick_hash(large, large.stat().st_size)
    assert quick_hash(large, large.stat().st_size) == quick_hash(
        same_edges, same_edges.stat().st_size
    )
    assert len(quick_hash(small, 100)) == 64


def test_progress_counts(tmp_path: Path) -> None:
    for i in range(600):
        (tmp_path / f"{i:03d}.mp3").write_bytes(b"")
    seen: list[int] = []

    found = list(discover(tmp_path, [], progress=seen.append))

    assert len(found) == 600 and seen == [250, 500, 600]
