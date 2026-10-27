"""Checks every format adapter must pass, plus test-only plan writing."""

from pathlib import Path

from djlib.adapters.contract import Adapter, ReadOptions, ReadResult, WriteOptions, WritePlan
from djlib.model.library import Library

TreeState = dict[str, tuple[bytes, int]]


def tree_state(location: Path) -> TreeState:
    """Bytes and modification time of every file under ``location`` (or of the file)."""
    if location.is_file():
        return {location.name: (location.read_bytes(), location.stat().st_mtime_ns)}
    return {
        str(p.relative_to(location)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(location.rglob("*"))
        if p.is_file()
    }


def assert_read_only(
    adapter: Adapter, location: Path, options: ReadOptions | None = None
) -> ReadResult:
    before = tree_state(location)
    result = adapter.read(location, options)
    assert tree_state(location) == before, f"{adapter.name}.read changed {location}"
    return result


def assert_plan_writes_nothing(
    adapter: Adapter, library: Library, location: Path, options: WriteOptions | None = None
) -> WritePlan:
    before = tree_state(location) if location.exists() else None
    plan = adapter.plan_write(library, location, options)
    after = tree_state(location) if location.exists() else None
    assert after == before, f"{adapter.name}.plan_write changed {location}"
    return plan


def write_plan_to_disk(plan: WritePlan) -> None:
    """Write a plan's files directly. For tests only: no hash checks or snapshots."""
    for change in plan.changes:
        change.path.parent.mkdir(parents=True, exist_ok=True)
        change.path.write_bytes(change.content)
