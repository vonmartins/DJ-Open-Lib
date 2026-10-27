import datetime
from importlib.metadata import version
from pathlib import Path

import pytest

from djlib.snapshots import SnapshotError, SnapshotStore
from djlib.snapshots import snapshot_store as module
from support.files import sha256

NML = b'<?xml version="1.0"?><NML VERSION="20"><COLLECTION ENTRIES="1"/></NML>\n'


def copy_path(store: SnapshotStore, target: str, snapshot_id: str, index: int) -> Path:
    return store.root / target / snapshot_id / "files" / str(index)


def test_single_file_target(snapshots: SnapshotStore, app_dir: Path) -> None:
    collection = app_dir / "collection.nml"
    collection.write_bytes(NML)
    before = collection.stat().st_mtime_ns

    snapshot = snapshots.create("traktor", [collection])

    assert sha256(copy_path(snapshots, "traktor", snapshot.id, 0)) == sha256(collection)
    assert snapshot.files[0].sha256 == sha256(collection)
    assert collection.read_bytes() == NML
    assert collection.stat().st_mtime_ns == before


def test_multi_file_target(snapshots: SnapshotStore, app_dir: Path) -> None:
    files = [app_dir / f"{name}.m3u" for name in ("a", "b", "c")]
    for index, path in enumerate(files):
        path.write_text(f"#EXTM3U\n/music/{index}.mp3\n", encoding="utf-8")

    snapshot = snapshots.create("m3u", files)

    for index, path in enumerate(files):
        assert copy_path(snapshots, "m3u", snapshot.id, index).read_bytes() == path.read_bytes()


def test_manifest_contents(app_dir: Path, tmp_path: Path) -> None:
    moment = datetime.datetime(2026, 10, 27, 10, 15, 0, 5, tzinfo=datetime.UTC)
    store = SnapshotStore(tmp_path / "snapshots", _clock=lambda: moment)
    (app_dir / "collection.nml").write_bytes(NML)

    snapshot = store.create("traktor", [app_dir / "collection.nml"])

    assert snapshot.id == "000001-20261027T101500Z"
    assert snapshot.target == "traktor"
    assert snapshot.created_at == moment
    assert snapshot.djlib_version == version("djlib")
    assert snapshot.reason is None
    (record,) = snapshot.files
    assert (record.path, record.present, record.size, record.method) == (
        str(app_dir / "collection.nml"),
        True,
        len(NML),
        "copy",
    )
    assert store.get("traktor", snapshot.id) == snapshot


def test_absent_file_recorded(snapshots: SnapshotStore, app_dir: Path) -> None:
    snapshot = snapshots.create("m3u", [app_dir / "new.m3u"])

    (record,) = snapshot.files
    assert record.present is False
    assert not (snapshots.root / "m3u" / snapshot.id / "files" / "0").exists()


def test_creation_is_all_or_nothing(
    snapshots: SnapshotStore, app_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = [app_dir / "a.m3u", app_dir / "b.m3u"]
    for path in files:
        path.write_text("x", encoding="utf-8")
    real_copy_in = module._copy_in  # pyright: ignore[reportPrivateUsage]
    calls: list[Path] = []

    def failing_copy_in(source: Path, copy: Path) -> module.FileRecord:
        calls.append(source)
        if len(calls) == 2:
            raise PermissionError(f"cannot read {source}")
        return real_copy_in(source, copy)

    monkeypatch.setattr(module, "_copy_in", failing_copy_in)

    with pytest.raises(SnapshotError, match="cannot read"):
        snapshots.create("m3u", files)

    assert snapshots.list("m3u") == []
    assert [p.name for p in (snapshots.root / "m3u").iterdir()] == []
    assert [p.read_text(encoding="utf-8") for p in files] == ["x", "x"]


def test_stale_temporary_directories_removed(snapshots: SnapshotStore, app_dir: Path) -> None:
    stale = snapshots.root / "traktor" / ".tmp-000009-20200101T000000Z"
    stale.mkdir(parents=True)
    (app_dir / "collection.nml").write_bytes(NML)

    snapshots.create("traktor", [app_dir / "collection.nml"])

    assert not stale.exists()


def test_reason_is_recorded(snapshots: SnapshotStore, app_dir: Path) -> None:
    snapshot = snapshots.create("t", [app_dir / "x"], reason="before export")
    assert snapshots.get("t", snapshot.id).reason == "before export"
