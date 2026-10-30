"""The optional parts of the adapter contract: target views and pre-write checks."""

import dataclasses
import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from support.files import tree_bytes
from tunedex.adapters.contract import (
    Capabilities,
    Detection,
    FileChange,
    ReadOptions,
    ReadResult,
    WriteOptions,
    WritePlan,
)
from tunedex.adapters.errors import AdapterError
from tunedex.model.library import Library
from tunedex.model.playlist import Playlist
from tunedex.planning import Engine, assume_yes
from tunedex.planning.tree import walk
from tunedex.snapshots import SnapshotStore


@dataclasses.dataclass
class FlatAdapter:
    """Writes the names of all playlists, flattened, to one file and gives that view."""

    check: Callable[[], None] | None = None
    name: str = "flat"
    capabilities: Capabilities = dataclasses.field(
        default_factory=lambda: Capabilities(track_fields=frozenset())
    )

    def detect(self, location: Path) -> Detection:
        return Detection(False, "never")

    def read(self, location: Path, options: ReadOptions | None = None) -> ReadResult:
        return ReadResult(library=Library())

    def plan_write(
        self, library: Library, location: Path, options: WriteOptions | None = None
    ) -> WritePlan:
        playlists = [
            Playlist(id=p.node.id, name=" / ".join(p.path), entries=p.node.entries)
            for p in walk(library)
            if isinstance(p.node, Playlist)
        ]
        path = location / "lists.txt"
        base = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        content = "\n".join(p.name for p in playlists).encode()
        return WritePlan(
            adapter=self.name,
            location=location,
            changes=(FileChange(path=path, content=content, base_sha256=base, description="x"),),
            view=Library(tracks=library.tracks, playlists=tuple(playlists)),
            check=self.check,
        )


def test_flattened_playlists(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    plan = engine.plan_export(FlatAdapter(), tmp_path / "out")

    assert [(n.change, n.path) for n in plan.nodes] == [
        ("added", ("Techno / Peak",)),
        ("added", ("House / Warm",)),
        ("added", ("Chill",)),
    ]
    view = plan.action.write_plan.view  # type: ignore[union-attr]
    assert view is not None and view.playlists[0].id == library["peak"].id


def test_check_fails(
    engine: Engine, snapshots: SnapshotStore, library: dict[str, Any], tmp_path: Path
) -> None:
    def refuse() -> None:
        raise AdapterError("quit the app first")

    plan = engine.plan_export(FlatAdapter(check=refuse), tmp_path / "out")
    before = tree_bytes(tmp_path / "out")

    with pytest.raises(AdapterError, match="quit the app first"):
        engine.apply(plan, assume_yes)

    assert tree_bytes(tmp_path / "out") == before
    assert snapshots.targets() == []


def test_check_passes(engine: Engine, library: dict[str, Any], tmp_path: Path) -> None:
    calls: list[int] = []
    plan = engine.plan_export(FlatAdapter(check=lambda: calls.append(1)), tmp_path / "out")

    assert engine.apply(plan, assume_yes).status == "applied"
    assert calls == [1]
    assert (tmp_path / "out" / "lists.txt").exists()
