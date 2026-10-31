from pathlib import Path

import pytest

from tunedex.snapshots import SnapshotStore


@pytest.fixture
def app_dir(tmp_path: Path) -> Path:
    """Where the files of a fake DJ app live."""
    directory = tmp_path / "app"
    directory.mkdir()
    return directory


@pytest.fixture
def snapshots(tmp_path: Path) -> SnapshotStore:
    return SnapshotStore(tmp_path / "snapshots")
