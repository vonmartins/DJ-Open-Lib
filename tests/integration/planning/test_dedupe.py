"""Reporting and merging duplicates (specs/duplicates)."""

from pathlib import Path
from typing import Any

import pytest

from tunedex.model.playlist import Playlist
from tunedex.model.track import Track
from tunedex.planning import Engine, assume_yes
from tunedex.snapshots import SnapshotStore
from tunedex.store import Store

from .conftest import NOW


@pytest.fixture
def trashed() -> list[str]:
    return []


@pytest.fixture
def engine(store: Store, snapshots: SnapshotStore, trashed: list[str]) -> Engine:
    def trash(path: str) -> None:
        trashed.append(path)
        Path(path).unlink()

    return Engine(store, snapshots, clock=lambda: NOW, _trash=trash)


@pytest.fixture
def music(tmp_path: Path) -> Path:
    folder = tmp_path / "music"
    folder.mkdir()
    return folder


def add(store: Store, music: Path, name: str, **fields: Any) -> Track:
    fields.setdefault("artist", "Phaeleh")
    fields.setdefault("title", "Numb")
    fields.setdefault("duration_us", 312_000_000)
    path = music / name
    path.write_bytes(b"audio")
    track = Track(path_origin=str(path), **fields)
    store.add_track(track)
    return track


def pair(store: Store, music: Path) -> tuple[Track, Track]:
    flac = add(store, music, "a.flac", file_format="flac")
    mp3 = add(store, music, "b.mp3", file_format="mp3", bitrate=320, label="Tempa")
    return flac, mp3


def test_report_read_only(engine: Engine, store: Store, music: Path) -> None:
    flac, mp3 = pair(store, music)
    add(store, music, "c.mp3", title="Lounge", duration_us=200_000_000)
    add(store, music, "d.mp3", title="Lounge", duration_us=201_000_000)
    store.add_node(Playlist(name="P", entries=(mp3.id, mp3.id)))
    revision = store.revision()

    groups = engine.find_duplicates()

    assert [g.name for g in groups] == ["Phaeleh - Lounge", "Phaeleh - Numb"]
    numb = groups[1]
    assert [c.track for c in numb.copies] == [flac, mp3]
    assert (numb.reason, numb.copies[1].playlists, numb.copies[0].present) == (
        "lossless",
        1,
        True,
    )
    assert store.revision() == revision


def test_file_trashed(engine: Engine, store: Store, music: Path, trashed: list[str]) -> None:
    flac, mp3 = pair(store, music)

    plan = engine.plan_merge()
    result = engine.apply(plan, assume_yes)

    assert trashed == [mp3.path_origin]
    assert [t.id for t in store.list_tracks()] == [flac.id]
    assert store.get_track(flac.id).label == "Tempa"
    assert [c.change for c in plan.tracks] == ["updated", "merged"]
    assert result.files_trashed == 1


def test_files_kept(engine: Engine, store: Store, music: Path, trashed: list[str]) -> None:
    flac, mp3 = pair(store, music)

    plan = engine.plan_merge(keep_files=True)
    engine.apply(plan, assume_yes)

    assert plan.trash == ()
    assert trashed == []
    assert Path(mp3.path_origin).exists()
    assert [t.id for t in store.list_tracks()] == [flac.id]


def test_another_track_kept(engine: Engine, store: Store, music: Path, trashed: list[str]) -> None:
    flac, mp3 = pair(store, music)
    (group,) = engine.find_duplicates()

    engine.apply(engine.plan_merge({group.key: mp3.id}), assume_yes)

    assert [t.id for t in store.list_tracks()] == [mp3.id]
    assert trashed == [flac.path_origin]


def test_skipped(engine: Engine, store: Store, music: Path) -> None:
    pair(store, music)
    (group,) = engine.find_duplicates()

    assert engine.plan_merge({group.key: "skip"}).empty


def test_file_from_beets(engine: Engine, store: Store, music: Path) -> None:
    add(store, music, "a.flac", file_format="flac")
    add(store, music, "b.mp3", unmapped={"beets": {"id": 7}})

    plan = engine.plan_merge()

    assert any("beets library" in w for w in plan.warnings)


def test_missing_file_not_trashed(engine: Engine, store: Store, music: Path) -> None:
    add(store, music, "a.flac", file_format="flac")
    store.add_track(Track(path_origin=str(music / "gone.mp3"), artist="Phaeleh", title="Numb"))

    plan = engine.plan_merge()

    assert plan.trash == ()
    assert [c.change for c in plan.tracks] == ["merged"]


def test_not_reported_again(engine: Engine, store: Store, music: Path) -> None:
    pair(store, music)
    (group,) = engine.find_duplicates()

    engine.apply(engine.plan_merge({group.key: "ignore"}), assume_yes)

    assert engine.find_duplicates() == ()
    assert engine.plan_merge().empty
    assert len(store.list_tracks()) == 2

    add(store, music, "c.mp3")
    (again,) = engine.find_duplicates()
    assert len(again.copies) == 3


def test_plan_changes_nothing_then_merged_twice(engine: Engine, store: Store, music: Path) -> None:
    flac, mp3 = pair(store, music)
    revision, before = store.revision(), store.load_library()

    plan = engine.plan_merge()

    assert (store.revision(), store.load_library()) == (revision, before)
    assert Path(mp3.path_origin).exists() and Path(flac.path_origin).exists()
    engine.apply(plan, assume_yes)
    assert engine.plan_merge().empty


def test_under_keeps_whole_groups_with_a_track_there(
    engine: Engine, store: Store, music: Path
) -> None:
    (music / "new").mkdir()
    (music / "old").mkdir()
    new = add(store, music, "new/a.mp3", bitrate=320)
    old = add(store, music, "old/a.mp3", bitrate=128)
    add(store, music, "old/c.mp3", title="Lounge", duration_us=200_000_000)
    add(store, music, "old/d.mp3", title="Lounge", duration_us=201_000_000)

    groups = engine.find_duplicates(under=music / "new")

    assert [{c.track.id for c in g.copies} for g in groups] == [{new.id, old.id}]
    plan = engine.plan_merge(under=music / "new")
    assert {c.track_id for c in plan.tracks if c.change == "merged"} == {old.id}
