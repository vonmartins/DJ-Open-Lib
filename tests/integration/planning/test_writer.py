from pathlib import Path

import pytest

from tunedex.planning import writer
from tunedex.planning.writer import DirectoryTracker, write_atomically


def test_creates_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "a.m3u8"
    write_atomically(target, b"one")
    write_atomically(target, b"two")

    assert target.read_bytes() == b"two"
    assert [p.name for p in tmp_path.iterdir()] == ["a.m3u8"]


def test_no_partial_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "a.m3u8"
    target.write_bytes(b"old")

    def fail(self: Path, other: Path) -> Path:
        raise OSError("disk unplugged")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="disk unplugged"):
        write_atomically(target, b"new")

    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["a.m3u8"]


def test_failed_write_leaves_no_temporary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(descriptor: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(writer.os, "fsync", fail)
    with pytest.raises(OSError, match="fsync failed"):
        write_atomically(tmp_path / "a.m3u8", b"new")

    assert list(tmp_path.iterdir()) == []


def test_tracker_removes_only_empty_created_directories(tmp_path: Path) -> None:
    (tmp_path / "existing").mkdir()
    tracker = DirectoryTracker()
    tracker.ensure(tmp_path / "existing" / "a" / "b")
    tracker.ensure(tmp_path / "c")
    (tmp_path / "c" / "kept.txt").write_text("x")

    tracker.remove_empty()

    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == [
        "c",
        "c/kept.txt",
        "existing",
    ]
