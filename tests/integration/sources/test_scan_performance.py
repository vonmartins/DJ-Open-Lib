"""Timing of a first scan and a rescan of 2,000 files (reported, not asserted)."""

import shutil
import time
from pathlib import Path

from djlib.sources.folder_scan import scan_folder
from djlib.store import Store
from support.audio import FORMATS, tagged_copy

COUNT = 2_000


def test_scan_timings(tmp_path: Path, store: Store) -> None:
    root = tmp_path / "music"
    templates = [tagged_copy(tmp_path / "templates", fmt, title=f"T {fmt}") for fmt in FORMATS]
    for index in range(COUNT):
        template = templates[index % len(templates)]
        target = root / f"{index % 40:02d}" / f"{index:05d}{template.suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, target)

    started = time.perf_counter()
    plan = scan_folder(store, root)
    store.apply_scan(plan.operations)
    first = time.perf_counter() - started

    started = time.perf_counter()
    rescan = scan_folder(store, root)
    second = time.perf_counter() - started

    assert len(plan.operations) == COUNT
    assert rescan.operations == ()
    print(f"\n{COUNT} files: first scan + apply {first:.2f}s, rescan {second:.2f}s")
