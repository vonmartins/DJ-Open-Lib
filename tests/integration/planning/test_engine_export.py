import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from support.files import tree_bytes
from tunedex.adapters.m3u import M3UAdapter
from tunedex.planning import (
    ApplyFailedError,
    Engine,
    PlanError,
    StaleTargetError,
    UnknownPlaylistError,
    assume_yes,
)
from tunedex.planning.model import NodeChange
from tunedex.snapshots import SnapshotStore
from tunedex.store import Store

M3U = M3UAdapter()


def decline(plan: object) -> bool:
    return False


def everything(tmp_path: Path) -> dict[str, dict[str, bytes | None]]:
    return {name: tree_bytes(tmp_path / name) for name in ("out", "snapshots")}


# Planning


def test_export_planned_writes_nothing(
    engine: Engine, store: Store, library: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    (out / "Chill.m3u8").parent.mkdir(parents=True)
    (out / "Chill.m3u8").write_bytes(b"#EXTM3U\n")
    before, database = everything(tmp_path), (tmp_path / "library.db").read_bytes()
    revision = store.revision()

    plan = engine.plan_export(M3U, out)

    assert not plan.empty
    assert everything(tmp_path) == before
    assert (tmp_path / "library.db").read_bytes() == database
    assert store.revision() == revision


def test_export_of_a_new_playlist(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    plan = engine.plan_export(M3U, tmp_path / "out", playlists=["Techno/Peak"])

    assert plan.nodes == (
        NodeChange(
            change="added",
            path=("Techno", "Peak"),
            kind="playlist",
            entries_added=("/music/a.mp3", "/music/b.mp3", "/music/c.mp3"),
        ),
    )
    assert [(f.path, f.action) for f in plan.files] == [
        (tmp_path / "out" / "Techno" / "Peak.m3u8", "create")
    ]
    assert plan.target.startswith("m3u-")


def test_losses_shown(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    plan = engine.plan_export(M3U, tmp_path / "out")

    (cues,) = [loss for loss in plan.losses if "cue" in loss.kind]
    assert cues.count == 1
    assert cues.examples == ("Artist - A",)


def test_unknown_playlist_path(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    with pytest.raises(UnknownPlaylistError, match="Techno/Peak"):
        engine.plan_export(M3U, tmp_path / "out", playlists=["Techno/Peek"])


def test_selected_and_modified_are_exclusive(engine: Engine, tmp_path: Path) -> None:
    with pytest.raises(PlanError):
        engine.plan_export(M3U, tmp_path, playlists=["A"], modified_only=True)


# Applying


def test_declined(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    plan = engine.plan_export(M3U, tmp_path / "out")

    result = engine.apply(plan, decline)

    assert result.status == "declined"
    assert everything(tmp_path) == {"out": {}, "snapshots": {}}


def test_empty_plan(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    engine.apply(engine.plan_export(M3U, tmp_path / "out"), assume_yes)
    before = everything(tmp_path)

    plan = engine.plan_export(M3U, tmp_path / "out")
    result = engine.apply(plan, assume_yes)

    assert plan.empty
    assert result.status == "nothing"
    assert everything(tmp_path) == before


def test_snapshot_taken(
    engine: Engine, snapshots: SnapshotStore, library: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    engine.apply(engine.plan_export(M3U, out, playlists=["Chill"]), assume_yes)
    old_chill = (out / "Chill.m3u8").read_bytes()
    store_track = dataclasses.replace(library["c"], title="C2")
    engine.store.update_track(store_track)

    plan = engine.plan_export(M3U, out, playlists=["Chill", "House"])
    result = engine.apply(plan, assume_yes)

    assert result.status == "applied"
    snapshot = snapshots.get(plan.target, result.snapshot or "")
    records = {Path(r.path).name: r for r in snapshot.files}
    assert records["Chill.m3u8"].present and records["Warm.m3u8"].present is False
    assert snapshot.reason == plan.title
    assert (out / "Chill.m3u8").read_bytes() != old_chill
    assert result.files_written == 2


def test_file_edited_after_planning(
    engine: Engine, library: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    engine.apply(engine.plan_export(M3U, out), assume_yes)
    engine.store.update_track(dataclasses.replace(library["c"], title="C2"))
    plan = engine.plan_export(M3U, out)
    (out / "Chill.m3u8").write_bytes(b"#EXTM3U\n# edited by hand\n")
    before = everything(tmp_path)

    with pytest.raises(StaleTargetError, match=r"Chill\.m3u8 changed"):
        engine.apply(plan, assume_yes)

    assert everything(tmp_path) == before


def test_file_created_after_planning(
    engine: Engine, library: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    plan = engine.plan_export(M3U, out, playlists=["Chill"])
    out.mkdir()
    (out / "Chill.m3u8").write_bytes(b"#EXTM3U\n")

    with pytest.raises(StaleTargetError, match="was created"):
        engine.apply(plan, assume_yes)

    assert (out / "Chill.m3u8").read_bytes() == b"#EXTM3U\n"


def test_fault_in_the_middle_of_an_export(
    make_engine: Callable[..., Engine], store: Store, library: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    make_engine().apply(make_engine().plan_export(M3U, out, playlists=["Chill"]), assume_yes)
    store.update_track(dataclasses.replace(library["c"], title="C2"))
    written: list[Path] = []

    def fail_on_third(path: Path, content: bytes) -> None:
        if len(written) == 2:
            raise OSError("injected failure")
        path.write_bytes(content)
        written.append(path)

    engine = make_engine(_write_file=fail_on_third)
    plan = engine.plan_export(M3U, out)
    assert len(plan.files) == 3
    before = tree_bytes(out)
    recorded = store.sync_state(plan.target)

    with pytest.raises(ApplyFailedError, match="restored to its previous state") as excinfo:
        engine.apply(plan, assume_yes)

    assert excinfo.value.restored
    assert len(written) == 2
    assert tree_bytes(out) == before  # same files, same bytes, no new directories
    assert store.sync_state(plan.target) == recorded


def test_restore_failure_names_the_snapshot(
    make_engine: Callable[..., Engine],
    snapshots: SnapshotStore,
    library: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(path: Path, content: bytes) -> None:
        raise OSError("injected failure")

    def broken_restore(snapshot: object) -> None:
        raise OSError("restore broken")

    engine = make_engine(_write_file=fail)
    plan = engine.plan_export(M3U, tmp_path / "out")
    monkeypatch.setattr(snapshots, "restore", broken_restore)

    with pytest.raises(ApplyFailedError, match="restore by hand with snapshot") as excinfo:
        engine.apply(plan, assume_yes)

    assert not excinfo.value.restored
    assert snapshots.get(plan.target, excinfo.value.snapshot)


# Sync modes and idempotence


def test_selected_playlist(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    out = tmp_path / "out"

    engine.apply(engine.plan_export(M3U, out, playlists=["Techno/Peak"]), assume_yes)

    assert list(tree_bytes(out)) == ["Techno", "Techno/Peak.m3u8"]


def test_modified_only(
    engine: Engine, store: Store, library: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    engine.apply(engine.plan_export(M3U, out), assume_yes)
    warm = library["warm"]
    store.update_node(dataclasses.replace(warm, entries=(*warm.entries, library["a"].id)))

    plan = engine.plan_export(M3U, out, modified_only=True)

    assert [f.path.name for f in plan.files] == ["Warm.m3u8"]
    assert [n.path for n in plan.nodes] == [("House", "Warm")]


def test_unchanged_library_skips_plan_write(
    engine: Engine, library: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    engine.apply(engine.plan_export(M3U, out), assume_yes)
    adapter = M3UAdapter()

    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("plan_write called")

    monkeypatch.setattr(adapter, "plan_write", unexpected)
    plan = engine.plan_export(adapter, out, modified_only=True)

    assert plan.empty


def test_different_targets(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    engine.apply(engine.plan_export(M3U, tmp_path / "a"), assume_yes)

    plan = engine.plan_export(M3U, tmp_path / "b", modified_only=True)

    assert len(plan.files) == 3


def test_failed_or_declined_apply_records_nothing(
    engine: Engine, store: Store, library: dict[str, Any], tmp_path: Path
) -> None:
    plan = engine.plan_export(M3U, tmp_path / "out")

    engine.apply(plan, decline)

    assert store.sync_state(plan.target) == {}


def test_extra_playlist_in_target_untouched(
    engine: Engine, library: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "Mine.m3u8").write_bytes(b"#EXTM3U\n/music/x.mp3\n")

    for kwargs in ({}, {"playlists": ["Chill"]}, {"modified_only": True}):
        plan = engine.plan_export(M3U, out, **kwargs)  # pyright: ignore[reportArgumentType]
        assert plan.untouched_nodes == 1
        assert all(f.path.name != "Mine.m3u8" for f in plan.files)
    engine.apply(engine.plan_export(M3U, out), assume_yes)
    assert (out / "Mine.m3u8").read_bytes() == b"#EXTM3U\n/music/x.mp3\n"


def test_export_twice(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    out = tmp_path / "out"
    engine.apply(engine.plan_export(M3U, out), assume_yes)

    assert engine.plan_export(M3U, out).empty
    assert engine.plan_export(M3U, out, modified_only=True).empty
