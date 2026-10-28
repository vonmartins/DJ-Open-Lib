"""Exports to targets that hold a collection: edits made in the target are respected."""

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

from djlib.adapters.contract import (
    Capabilities,
    Detection,
    FileChange,
    ReadOptions,
    ReadResult,
    WriteOptions,
    WritePlan,
)
from djlib.model.library import Library
from djlib.model.track import Track
from djlib.planning import Engine, assume_yes
from djlib.snapshots import SnapshotStore
from djlib.store import Store

FIELDS = ("title", "genre", "bpm", "duration_us")


class JsonCollection:
    """A collection file: one JSON object per track. Durations are not updated in place."""

    name = "jsoncol"
    capabilities = Capabilities(
        track_fields=frozenset(FIELDS),
        updated_fields=frozenset({"title", "genre", "bpm"}),
        collection=True,
    )

    def detect(self, location: Path) -> Detection:
        return Detection(location.is_file(), "")

    def read(self, location: Path, options: ReadOptions | None = None) -> ReadResult:
        return ReadResult(library=_library(json.loads(location.read_text())))

    def plan_write(
        self, library: Library, location: Path, options: WriteOptions | None = None
    ) -> WritePlan:
        rows = json.loads(location.read_text()) if location.exists() else {}
        for track in library.tracks.values():
            row = rows.setdefault(track.path, {})
            for name in FIELDS:
                if track.path in rows and row and name == "duration_us":
                    continue
                row[name] = getattr(track, name)
        content = json.dumps(rows, sort_keys=True).encode()
        base = hashlib.sha256(location.read_bytes()).hexdigest() if location.exists() else None
        changes = ()
        if base is None or location.read_bytes() != content:
            changes = (
                FileChange(path=location, content=content, base_sha256=base, description=""),
            )
        written = _library(
            {p: r for p, r in rows.items() if p in {t.path for t in library.tracks.values()}}
        )
        return WritePlan(adapter=self.name, location=location, changes=changes, view=written)


def _library(rows: dict[str, dict[str, Any]]) -> Library:
    return Library.build(Track(path_origin=path, **row) for path, row in rows.items())


ADAPTER = JsonCollection()


def write_target(path: Path, **tracks: dict[str, Any]) -> None:
    path.write_text(json.dumps({f"/music/{k}.mp3": v for k, v in tracks.items()}, sort_keys=True))


def target(path: Path) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text())


def export(engine: Engine, path: Path) -> Any:
    plan = engine.plan_export(ADAPTER, path)
    engine.apply(plan, assume_yes)
    return plan


def edit(store: Store, **values: Any) -> None:
    (track,) = store.list_tracks()
    store.update_track(dataclasses.replace(track, **values))


def test_never_imported_fills_only_empty_fields(
    engine: Engine, store: Store, tmp_path: Path
) -> None:
    path = tmp_path / "col.json"
    write_target(path, a={"title": "Mixxx title"})
    store.add_track(Track(path_origin="/music/a.mp3", title="djlib title", bpm=128.0))

    plan = export(engine, path)

    assert target(path)["/music/a.mp3"] == {"title": "Mixxx title", "bpm": 128.0, "genre": None}
    assert [c.field for c in plan.conflicts] == []


def test_target_edit_kept(engine: Engine, store: Store, tmp_path: Path) -> None:
    path = tmp_path / "col.json"
    store.add_track(Track(path_origin="/music/a.mp3", genre="Techno"))
    export(engine, path)
    edit(store, genre="House")
    rows = target(path)
    rows["/music/a.mp3"]["genre"] = "Minimal"
    path.write_text(json.dumps(rows, sort_keys=True))

    plan = export(engine, path)

    assert [(c.field, c.library_value, c.file_value) for c in plan.conflicts] == [
        ("genre", "House", "Minimal")
    ]
    assert target(path)["/music/a.mp3"]["genre"] == "Minimal"
    # Reported again until an import settles it.
    assert [c.field for c in engine.plan_export(ADAPTER, path).conflicts] == ["genre"]


def test_conflict_settled_by_an_import(engine: Engine, store: Store, tmp_path: Path) -> None:
    path = tmp_path / "col.json"
    store.add_track(Track(path_origin="/music/a.mp3", genre="Techno"))
    export(engine, path)
    edit(store, genre="House")
    rows = target(path)
    rows["/music/a.mp3"]["genre"] = "Minimal"
    path.write_text(json.dumps(rows, sort_keys=True))

    engine.apply(engine.plan_import(ADAPTER, path), assume_yes)
    plan = export(engine, path)

    assert plan.conflicts == ()
    assert target(path)["/music/a.mp3"]["genre"] == "House"


def test_library_edit_written(engine: Engine, store: Store, tmp_path: Path) -> None:
    path = tmp_path / "col.json"
    store.add_track(Track(path_origin="/music/a.mp3", bpm=126.0))
    export(engine, path)
    edit(store, bpm=128.0)

    plan = export(engine, path)

    assert target(path)["/music/a.mp3"]["bpm"] == 128.0
    assert [(f.field, f.before, f.after) for f in plan.tracks[0].fields] == [("bpm", 126.0, 128.0)]


def test_technical_field_not_merged(engine: Engine, store: Store, tmp_path: Path) -> None:
    path = tmp_path / "col.json"
    write_target(path, a={"duration_us": 1_000_000})
    store.add_track(Track(path_origin="/music/a.mp3", duration_us=2_000_000))
    export(engine, path)
    edit(store, title="New")

    plan = export(engine, path)

    assert plan.conflicts == ()
    assert target(path)["/music/a.mp3"]["duration_us"] == 1_000_000


def test_bases_recorded_with_the_sync_state(engine: Engine, store: Store, tmp_path: Path) -> None:
    path = tmp_path / "col.json"
    store.add_track(Track(path_origin="/music/a.mp3", title="A", bpm=128.0))

    plan = export(engine, path)

    info = store.source(plan.target)
    assert info is not None and info.root_node_id is None
    (values,) = store.source_values(plan.target).values()
    assert values["bpm"] == 128.0 and values["title"] == "A"
    reimport = engine.plan_import(ADAPTER, path)
    assert (reimport.tracks, reimport.conflicts) == ((), ())


def test_declined_or_failed_apply_records_nothing(
    engine: Engine, store: Store, snapshots: SnapshotStore, tmp_path: Path
) -> None:
    path = tmp_path / "col.json"
    store.add_track(Track(path_origin="/music/a.mp3", title="A"))
    plan = engine.plan_export(ADAPTER, path)

    assert engine.apply(plan, lambda _plan: False).status == "declined"

    assert store.source(plan.target) is None
    assert store.source_values(plan.target) == {}
