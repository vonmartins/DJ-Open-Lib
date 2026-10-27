from pathlib import Path

import pytest

from djlib.snapshots import RestoreError, SnapshotStore
from djlib.snapshots import snapshot_store as module


def three_files(app_dir: Path) -> list[Path]:
    return [app_dir / f"{name}.m3u" for name in ("a", "b", "c")]


def write(files: list[Path], content: str) -> None:
    for path in files:
        path.write_text(f"{content} {path.name}", encoding="utf-8")


def contents(files: list[Path]) -> list[str]:
    return [p.read_text(encoding="utf-8") for p in files]


def fail_replace_on(monkeypatch: pytest.MonkeyPatch, failing_calls: set[int]) -> None:
    real_replace = module._replace_file  # pyright: ignore[reportPrivateUsage]
    calls = 0

    def replace(copy: Path, target: Path, sha256: str) -> None:
        nonlocal calls
        calls += 1
        if calls in failing_calls:
            raise PermissionError(f"{target} is locked")
        real_replace(copy, target, sha256)

    monkeypatch.setattr(module, "_replace_file", replace)


def test_failure_midway_rolls_back(
    snapshots: SnapshotStore, app_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = three_files(app_dir)
    write(files, "old")
    snapshot = snapshots.create("m3u", files)
    write(files, "current")
    fail_replace_on(monkeypatch, {2})

    with pytest.raises(RestoreError, match="put back") as excinfo:
        snapshots.restore(snapshot)

    assert excinfo.value.rolled_back is True
    assert contents(files) == ["current a.m3u", "current b.m3u", "current c.m3u"]


def test_failed_rollback_is_reported(
    snapshots: SnapshotStore, app_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = three_files(app_dir)
    write(files, "old")
    snapshot = snapshots.create("m3u", files)
    write(files, "current")
    fail_replace_on(monkeypatch, set(range(2, 100)))

    with pytest.raises(RestoreError) as excinfo:
        snapshots.restore(snapshot)

    pre_restore = snapshots.list("m3u")[0]
    assert pre_restore.reason == "pre-restore"
    assert excinfo.value.rolled_back is False
    assert pre_restore.id in str(excinfo.value)
