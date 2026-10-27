from pathlib import Path

import pytest

from djlib.snapshots import SnapshotCorruptError, SnapshotError, SnapshotStore
from djlib.store import Store


def damaged_setup(snapshots: SnapshotStore, app_dir: Path) -> tuple[Path, Path]:
    collection = app_dir / "collection.nml"
    collection.write_text("original", encoding="utf-8")
    snapshot = snapshots.create("traktor", [collection])
    collection.write_text("current", encoding="utf-8")
    return collection, snapshots.root / "traktor" / snapshot.id / "files" / "0"


def test_damaged_snapshot(snapshots: SnapshotStore, app_dir: Path) -> None:
    collection, copy = damaged_setup(snapshots, app_dir)
    copy.write_text("tampered", encoding="utf-8")
    (snapshot,) = snapshots.list("traktor")

    with pytest.raises(SnapshotCorruptError, match=r"collection\.nml"):
        snapshots.restore(snapshot)

    assert collection.read_text(encoding="utf-8") == "current"
    assert len(snapshots.list("traktor")) == 1


def test_same_size_tampering_detected(snapshots: SnapshotStore, app_dir: Path) -> None:
    _, copy = damaged_setup(snapshots, app_dir)
    copy.write_text("ORIGINAL", encoding="utf-8")
    (snapshot,) = snapshots.list("traktor")

    with pytest.raises(SnapshotCorruptError):
        snapshots.verify(snapshot)


def test_missing_copy(snapshots: SnapshotStore, app_dir: Path) -> None:
    collection, copy = damaged_setup(snapshots, app_dir)
    copy.unlink()
    (snapshot,) = snapshots.list("traktor")

    with pytest.raises(SnapshotCorruptError, match="missing"):
        snapshots.restore(snapshot)
    assert collection.read_text(encoding="utf-8") == "current"


@pytest.mark.parametrize("suffix", ["-journal", "-wal"])
def test_database_with_journal_refused(
    snapshots: SnapshotStore, app_dir: Path, suffix: str
) -> None:
    database = app_dir / "library.db"
    Store.open(database).close()
    snapshot = snapshots.create("library", [database])
    before = database.read_bytes()
    Path(f"{database}{suffix}").write_bytes(b"hot journal")

    with pytest.raises(SnapshotError, match=suffix):
        snapshots.restore(snapshot)
    assert database.read_bytes() == before
    assert len(snapshots.list("library")) == 1
