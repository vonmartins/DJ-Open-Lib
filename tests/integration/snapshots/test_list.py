import datetime
from pathlib import Path

import pytest

from tunedex.snapshots import SnapshotError, SnapshotStore

FROZEN = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.UTC)


def test_newest_first(snapshots: SnapshotStore, app_dir: Path) -> None:
    file = app_dir / "collection.nml"
    created = []
    for content in ("one", "two", "three"):
        file.write_text(content, encoding="utf-8")
        created.append(snapshots.create("traktor", [file]))

    assert [s.id for s in snapshots.list("traktor")] == [s.id for s in reversed(created)]


def test_same_clock_tick_keeps_order(tmp_path: Path, app_dir: Path) -> None:
    store = SnapshotStore(tmp_path / "snapshots", _clock=lambda: FROZEN)
    first = store.create("traktor", [app_dir / "a"])
    second = store.create("traktor", [app_dir / "a"])

    assert first.id != second.id
    assert [s.id for s in store.list("traktor")] == [second.id, first.id]


def test_targets_are_separate(snapshots: SnapshotStore, app_dir: Path) -> None:
    traktor = snapshots.create("traktor", [app_dir / "collection.nml"])
    snapshots.create("rekordbox", [app_dir / "rekordbox.xml"])

    assert snapshots.list("traktor") == [traktor]


def test_unknown_target_lists_nothing(snapshots: SnapshotStore) -> None:
    assert snapshots.list("nothing") == []


def test_temporary_and_invalid_directories_ignored(snapshots: SnapshotStore, app_dir: Path) -> None:
    valid = snapshots.create("traktor", [app_dir / "a"])
    target_dir = snapshots.root / "traktor"
    (target_dir / ".tmp-000005-20261027T120000Z").mkdir()
    broken = target_dir / "000006-20261027T120000Z"
    broken.mkdir()
    (broken / "manifest.json").write_text("{not json", encoding="utf-8")
    (target_dir / "notes").mkdir()

    assert snapshots.list("traktor") == [valid]


def test_listing_needs_only_the_snapshot_directory(tmp_path: Path, app_dir: Path) -> None:
    SnapshotStore(tmp_path / "snapshots").create("traktor", [app_dir / "a"])

    assert len(SnapshotStore(tmp_path / "snapshots").list("traktor")) == 1


def test_get_unknown_snapshot(snapshots: SnapshotStore) -> None:
    with pytest.raises(SnapshotError):
        snapshots.get("traktor", "000001-20261027T120000Z")


def test_targets(snapshots: SnapshotStore, app_dir: Path) -> None:
    assert snapshots.targets() == []
    (app_dir / "a.m3u").write_text("x")
    snapshots.create("traktor", [app_dir / "a.m3u"])
    snapshots.create("library", [app_dir / "a.m3u"])
    (snapshots.root / "Not A Target").mkdir()

    assert snapshots.targets() == ["library", "traktor"]
