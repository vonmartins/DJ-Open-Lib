import datetime
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tunedex.model.cue import Cue, CueKind
from tunedex.model.playlist import Folder, Playlist
from tunedex.model.track import Track
from tunedex.planning import Engine
from tunedex.snapshots import SnapshotStore
from tunedex.store import Store

NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.UTC)


@pytest.fixture
def snapshots(tmp_path: Path) -> SnapshotStore:
    return SnapshotStore(tmp_path / "snapshots", _clock=lambda: NOW, _version="0.0.0")


@pytest.fixture
def engine(store: Store, snapshots: SnapshotStore) -> Engine:
    return Engine(store, snapshots, clock=lambda: NOW)


@pytest.fixture
def make_engine(store: Store, snapshots: SnapshotStore) -> Callable[..., Engine]:
    def make(**kwargs: object) -> Engine:
        return Engine(store, snapshots, clock=lambda: NOW, **kwargs)  # pyright: ignore[reportArgumentType]

    return make


@pytest.fixture
def library(store: Store) -> dict[str, Any]:
    """Tracks a, b, c with playlists Techno/Peak (a, b, c), House/Warm (b) and Chill (c)."""
    cue = Cue(kind=CueKind.HOT, start_us=1_000_000, slot=0)
    a = Track(path_origin="/music/a.mp3", artist="Artist", title="A", cues=(cue,))
    b = Track(path_origin="/music/b.mp3", artist="Artist", title="B")
    c = Track(path_origin="/music/c.mp3", title="C")
    for track in (a, b, c):
        store.add_track(track)
    peak = Playlist(name="Peak", entries=(a.id, b.id, c.id))
    warm = Playlist(name="Warm", entries=(b.id,))
    chill = Playlist(name="Chill", entries=(c.id,))
    techno, house = Folder(name="Techno", children=(peak,)), Folder(name="House", children=(warm,))
    for node in (techno, house, chill):
        store.add_node(node)
    return {"a": a, "b": b, "c": c, "peak": peak, "warm": warm, "chill": chill, "techno": techno}
