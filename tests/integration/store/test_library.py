from collections.abc import Iterable

import pytest

from support.strategies import synthetic_library
from tunedex.model.ids import NodeId
from tunedex.model.library import Library
from tunedex.model.playlist import Node, Playlist
from tunedex.model.track import Track
from tunedex.store import ConflictError, Store
from tunedex.store.repository import Store as StoreClass


def test_empty_store_loads_empty_library(store: Store) -> None:
    assert store.load_library() == Library()


def test_replace_then_load(store: Store) -> None:
    library = synthetic_library(50, seed=3)

    store.replace_library(library)

    assert store.load_library() == library


def test_replace_discards_previous_content(store: Store) -> None:
    store.replace_library(synthetic_library(20, seed=1))
    smaller = synthetic_library(5, seed=2)

    store.replace_library(smaller)

    assert store.load_library() == smaller


def test_failure_during_save_leaves_content_unchanged(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = synthetic_library(30, seed=4)
    store.replace_library(original)

    def fail(_self: Store, _nodes: Iterable[tuple[NodeId | None, int, Node]]) -> None:
        raise RuntimeError("disk unplugged")

    monkeypatch.setattr(StoreClass, "_insert_nodes", fail)
    with pytest.raises(RuntimeError):
        store.replace_library(synthetic_library(10, seed=5))
    monkeypatch.undo()

    assert store.load_library() == original


def test_failed_track_add_leaves_store_unchanged(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3")
    store.add_track(track)
    store.add_node(Playlist(name="p", entries=(track.id,)))
    before = store.load_library()

    with pytest.raises(ConflictError):
        store.add_track(Track(path_origin="/music/a.mp3"))
    assert store.load_library() == before
