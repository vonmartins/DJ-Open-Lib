from pathlib import Path

from tunedex.snapshots import SnapshotStore


def fill(store: SnapshotStore, target: str, file: Path, count: int) -> list[str]:
    ids: list[str] = []
    for index in range(count):
        file.write_text(str(index), encoding="utf-8")
        ids.append(store.create(target, [file]).id)
    return ids


def test_default_retention(snapshots: SnapshotStore, app_dir: Path) -> None:
    ids = fill(snapshots, "traktor", app_dir / "collection.nml", 11)

    remaining = [s.id for s in snapshots.list("traktor")]
    assert len(remaining) == 10
    assert ids[0] not in remaining
    assert remaining == list(reversed(ids[1:]))
    assert not [p for p in (snapshots.root / "traktor").iterdir() if p.name.startswith(".tmp-")]


def test_other_targets_untouched(tmp_path: Path, app_dir: Path) -> None:
    store = SnapshotStore(tmp_path / "snapshots", keep=2)
    rekordbox = fill(store, "rekordbox", app_dir / "rekordbox.xml", 3)
    fill(store, "traktor", app_dir / "collection.nml", 5)

    assert [s.id for s in store.list("rekordbox")] == list(reversed(rekordbox[1:]))
    assert len(store.list("traktor")) == 2


def test_prune_reports_deleted_and_respects_protection(tmp_path: Path, app_dir: Path) -> None:
    store = SnapshotStore(tmp_path / "snapshots", keep=5)
    ids = fill(store, "traktor", app_dir / "collection.nml", 4)
    store.keep = 1

    deleted = store.prune("traktor", protect={ids[0]})

    assert deleted == [ids[2], ids[1]]
    assert [s.id for s in store.list("traktor")] == [ids[3], ids[0]]


def test_restore_with_keep_one(tmp_path: Path, app_dir: Path) -> None:
    store = SnapshotStore(tmp_path / "snapshots", keep=1)
    collection = app_dir / "collection.nml"
    collection.write_text("A", encoding="utf-8")
    snapshot = store.create("traktor", [collection])
    collection.write_text("B", encoding="utf-8")

    result = store.restore(snapshot)

    assert collection.read_text(encoding="utf-8") == "A"
    assert [s.id for s in store.list("traktor")] == [result.pre_restore.id, snapshot.id]
    store.create("traktor", [collection])
    assert len(store.list("traktor")) == 1
