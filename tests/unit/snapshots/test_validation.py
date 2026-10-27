from pathlib import Path

import pytest

from djlib.snapshots import DEFAULT_KEEP, SnapshotStore


def test_default_keep_is_ten(tmp_path: Path) -> None:
    assert SnapshotStore(tmp_path).keep == DEFAULT_KEEP == 10


@pytest.mark.parametrize("keep", [0, -1, 1.5, True, "3"])
def test_invalid_retention_rejected(tmp_path: Path, keep: object) -> None:
    with pytest.raises(ValueError, match="keep"):
        SnapshotStore(tmp_path, keep=keep)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("target", ["", "Traktor", "../x", "a/b", "-x", "a" * 65, "a b"])
def test_invalid_target_names(tmp_path: Path, target: str) -> None:
    with pytest.raises(ValueError, match="target"):
        SnapshotStore(tmp_path).create(target, [tmp_path / "f"])


@pytest.mark.parametrize("target", ["traktor", "rekordbox-xml", "library", "m3u.export", "a1_b"])
def test_valid_target_names(tmp_path: Path, target: str) -> None:
    assert SnapshotStore(tmp_path).list(target) == []


def test_relative_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        SnapshotStore(tmp_path).create("t", [Path("relative.nml")])


def test_duplicate_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="twice"):
        SnapshotStore(tmp_path).create("t", [tmp_path / "a", tmp_path / "a"])


def test_directory_rejected(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    with pytest.raises(ValueError, match="directory"):
        SnapshotStore(tmp_path).create("t", [tmp_path / "folder"])


def test_empty_target_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SnapshotStore(tmp_path).create("t", [])
