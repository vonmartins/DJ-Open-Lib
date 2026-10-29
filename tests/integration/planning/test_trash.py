"""Plans that move audio files to the trash (specs/plan-apply)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from djlib.model.track import Track
from djlib.planning import Engine, assume_yes, render_text, to_json
from djlib.planning.model import LIBRARY_TARGET, LibraryAction, Plan, TrackChange, TrashFile
from djlib.snapshots import SnapshotStore
from djlib.store import Store
from djlib.store.operations import MergeTracks

from .conftest import NOW


def file(tmp_path: Path, name: str, content: bytes = b"audio") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def merge_plan(store: Store, kept: Track, gone: Track, *files: Path) -> Plan:
    trash = tuple(TrashFile(str(f), f.stat().st_size, f.stat().st_mtime_ns) for f in files)
    change = TrackChange(
        change="merged", track_id=gone.id, path=gone.path, name="b", merged_into=kept.path
    )
    action = LibraryAction(
        operations=(MergeTracks(kept, (gone.id,)),), base_revision=store.revision(), trash=trash
    )
    return Plan(target=LIBRARY_TARGET, title="merge duplicates", action=action, tracks=(change,))


@pytest.fixture
def trashed() -> list[str]:
    return []


@pytest.fixture
def trashing(store: Store, snapshots: SnapshotStore, trashed: list[str]) -> Engine:
    def trash(path: str) -> None:
        trashed.append(path)
        Path(path).unlink()

    return Engine(store, snapshots, clock=lambda: NOW, _trash=trash)


def tracks(store: Store, tmp_path: Path) -> tuple[Track, Track, Path]:
    kept_file, gone_file = file(tmp_path, "a.flac"), file(tmp_path, "b.mp3", b"x" * 2_500_000)
    kept, gone = Track(path_origin=str(kept_file)), Track(path_origin=str(gone_file))
    store.add_track(kept)
    store.add_track(gone)
    return kept, gone, gone_file


def test_merge_shown(store: Store, tmp_path: Path) -> None:
    kept, gone, gone_file = tracks(store, tmp_path)

    plan = merge_plan(store, kept, gone, gone_file)

    text = render_text(plan)
    assert f"= b  {gone.path} → merged into {kept.path}" in text
    assert "Files to move to the trash: 1 (2.5 MB)" in text
    document = to_json(plan)
    assert document["trash"] == [{"path": str(gone_file), "bytes": 2_500_000}]
    assert document["tracks"][0]["merged_into"] == kept.path  # type: ignore[index]


def test_files_moved_after_the_library(
    trashing: Engine, store: Store, tmp_path: Path, trashed: list[str]
) -> None:
    kept, gone, gone_file = tracks(store, tmp_path)

    result = trashing.apply(merge_plan(store, kept, gone, gone_file), assume_yes)

    assert [t.id for t in store.list_tracks()] == [kept.id]
    assert trashed == [str(gone_file)]
    assert (result.files_trashed, result.warnings) == (1, ())


def test_changed_file_left_alone(
    trashing: Engine, store: Store, tmp_path: Path, trashed: list[str]
) -> None:
    kept, gone, gone_file = tracks(store, tmp_path)
    plan = merge_plan(store, kept, gone, gone_file)
    gone_file.write_bytes(b"changed")

    result = trashing.apply(plan, assume_yes)

    assert trashed == []
    assert gone_file.exists()
    assert result.files_trashed == 0
    assert "changed since the plan was made" in result.warnings[0]
    assert [t.id for t in store.list_tracks()] == [kept.id]


def test_trash_not_available(store: Store, snapshots: SnapshotStore, tmp_path: Path) -> None:
    def broken(_path: str) -> None:
        raise OSError("no trash on this volume")

    engine = Engine(store, snapshots, clock=lambda: NOW, _trash=broken)
    kept, gone, gone_file = tracks(store, tmp_path)

    result = engine.apply(merge_plan(store, kept, gone, gone_file), assume_yes)

    assert gone_file.exists()
    assert "no trash on this volume" in result.warnings[0]
    assert [t.id for t in store.list_tracks()] == [kept.id]


def test_restoring_the_library(
    trashing: Engine, store: Store, snapshots: SnapshotStore, tmp_path: Path
) -> None:
    kept, gone, gone_file = tracks(store, tmp_path)
    result = trashing.apply(merge_plan(store, kept, gone, gone_file), assume_yes)
    path = store.path
    store.close()

    assert result.snapshot is not None and path is not None
    snapshots.restore(snapshots.get(LIBRARY_TARGET, result.snapshot))

    with Store.open(path) as restored:
        assert {t.id for t in restored.list_tracks()} == {kept.id, gone.id}
    assert not gone_file.exists()


@pytest.mark.skipif(sys.platform != "linux", reason="would use the user's own trash")
def test_real_trash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    target = file(tmp_path, "b.mp3")
    code = "import sys; from send2trash import send2trash; send2trash(sys.argv[1])"
    # The home trash is used for files on the home's device: both point into tmp_path.
    environment = {**os.environ, "HOME": str(tmp_path), "XDG_DATA_HOME": str(data)}
    done = subprocess.run(
        [sys.executable, "-c", code, str(target)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        pytest.skip(f"no trash available here: {done.stderr.strip()[-200:]}")

    assert not target.exists()
    assert (data / "Trash" / "files" / "b.mp3").exists()
