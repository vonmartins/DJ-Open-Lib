import shutil
from pathlib import Path

import pytest

from support.audio import CLIPS
from support.files import sha256
from tunedex.snapshots import SnapshotError, SnapshotStore
from tunedex.snapshots.manifest import load_manifest
from tunedex.tagwrite.regions import audio_region
from tunedex.tagwrite.writer import write_tags

CLIP_NAMES = [
    "tagged-v24.mp3",
    "tagged-v23-v1.mp3",
    "tagged-ape.mp3",
    "tagged.flac",
    "tagged.wav",
    "tagged.aiff",
]


def _copies(directory: Path, names: list[str]) -> list[Path]:
    paths: list[Path] = []
    for name in names:
        path = directory / name
        shutil.copyfile(CLIPS / name, path)
        paths.append(path)
    return paths


def test_a_tag_snapshot_holds_only_the_bytes_outside_the_audio(
    snapshots: SnapshotStore, app_dir: Path
) -> None:
    (path,) = _copies(app_dir, ["tagged-v24.mp3"])
    clip = path.read_bytes()
    region = audio_region(path)
    path.write_bytes(clip[: region.end] + clip[region.start : region.end] * 2000)  # ~1.7 MB

    snapshot = snapshots.create_tags("tags", [path])

    copy = snapshots.root / "tags" / snapshot.id / "files" / "0"
    assert copy.stat().st_size == region.start
    (record,) = snapshot.files
    assert (record.method, record.size, record.sha256) == (
        "tags",
        path.stat().st_size,
        sha256(path),
    )
    assert snapshots.list("tags") == [snapshot]
    manifest = (snapshots.root / "tags" / snapshot.id / "manifest.json").read_text("utf-8")
    assert load_manifest(manifest) == snapshot


@pytest.mark.parametrize("name", CLIP_NAMES)
def test_restoring_undoes_a_write_byte_for_byte(
    snapshots: SnapshotStore, app_dir: Path, name: str
) -> None:
    (path,) = _copies(app_dir, [name])
    before = sha256(path)
    snapshot = snapshots.create_tags("tags", [path], reason="write tags")
    write_tags(path, {"title": "x" * 5000, "artist": None})
    assert sha256(path) != before

    result = snapshots.restore(snapshot)

    assert sha256(path) == before
    assert result.pre_restore.reason == "pre-restore"
    snapshots.restore(result.pre_restore)  # the restore itself can be undone
    assert sha256(path) != before


def test_a_restore_is_refused_when_the_audio_changed(
    snapshots: SnapshotStore, app_dir: Path
) -> None:
    first, second = _copies(app_dir, ["tagged-v24.mp3", "tagged.flac"])
    snapshot = snapshots.create_tags("tags", [first, second])
    write_tags(first, {"title": "Galaxy"})
    write_tags(second, {"title": "Galaxy"})
    data, region = bytearray(second.read_bytes()), audio_region(second)
    data[region.end - 1] ^= 0xFF  # re-encoded: other audio
    second.write_bytes(bytes(data))
    written = sha256(first)

    with pytest.raises(SnapshotError, match=r"tagged\.flac") as raised:
        snapshots.restore(snapshot)

    assert "tagged-v24.mp3" not in str(raised.value)
    assert sha256(first) == written
    assert len(snapshots.list("tags")) == 1  # no pre-restore snapshot either


def test_a_restore_is_refused_when_a_file_is_missing(
    snapshots: SnapshotStore, app_dir: Path
) -> None:
    (path,) = _copies(app_dir, ["tagged.wav"])
    snapshot = snapshots.create_tags("tags", [path])
    path.unlink()
    with pytest.raises(SnapshotError, match=r"tagged\.wav"):
        snapshots.restore(snapshot)


def test_tags_of_unsupported_or_missing_files_are_not_snapshotted(
    snapshots: SnapshotStore, app_dir: Path
) -> None:
    (m4a,) = _copies(app_dir, ["tagged.m4a"])
    with pytest.raises(SnapshotError, match="not supported"):
        snapshots.create_tags("tags", [m4a])
    with pytest.raises(SnapshotError, match="missing"):
        snapshots.create_tags("tags", [app_dir / "gone.mp3"])
    assert snapshots.list("tags") == []


def test_restore_files_puts_back_only_those(snapshots: SnapshotStore, app_dir: Path) -> None:
    first, second = _copies(app_dir, ["tagged-v24.mp3", "tagged.aiff"])
    before = sha256(first)
    snapshot = snapshots.create_tags("tags", [first, second])
    write_tags(first, {"title": "Galaxy"})
    untouched = second.stat().st_mtime_ns

    snapshots.restore_files(snapshot, {str(first)})

    assert sha256(first) == before
    assert second.stat().st_mtime_ns == untouched
    assert len(snapshots.list("tags")) == 1


def test_tag_snapshots_are_pruned_like_others(tmp_path: Path, app_dir: Path) -> None:
    store = SnapshotStore(tmp_path / "snapshots", keep=2)
    (path,) = _copies(app_dir, ["tagged.flac"])
    for _ in range(3):
        store.create_tags("tags", [path])
    assert [s.sequence for s in store.list("tags")] == [3, 2]
