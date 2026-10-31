"""Merged duplicates do not come back on imports and scans (specs/library-import, scan)."""

from pathlib import Path

from support.audio import tagged_copy
from support.beets import BeetsDatabase
from tunedex.model.paths import normalize_path
from tunedex.planning import Engine, assume_yes
from tunedex.sources.beets import BeetsSource
from tunedex.store import Store

BEETS = BeetsSource()


def test_merged_item_not_brought_back(engine: Engine, store: Store, tmp_path: Path) -> None:
    music = tmp_path / "music"
    flac = tagged_copy(music, "flac", name="numb.flac", artist="Phaeleh", title="Numb")
    mp3 = tagged_copy(music, "mp3", name="numb.mp3", artist="Phaeleh", title="Numb")
    engine.apply(engine.plan_scan(music), assume_yes)
    beets = BeetsDatabase(tmp_path / "beets" / "library.db")
    beets.add_item(str(mp3), artist="Phaeleh", title="Numb", label="Tempa")
    engine.apply(engine.plan_import(BEETS, beets.path), assume_yes)
    kept = store.find_track_by_path(normalize_path(str(flac)))
    assert kept is not None

    engine.apply(engine.plan_merge(keep_files=True), assume_yes)
    mp3.unlink()  # as if it was trashed
    plan = engine.plan_import(BEETS, beets.path)
    engine.apply(plan, assume_yes)

    (track,) = store.list_tracks()
    assert track.id == kept.id and track.path == kept.path
    assert track.label == "Tempa"
    assert not any("do not exist" in w for w in plan.warnings)
    assert engine.plan_import(BEETS, beets.path).empty


def test_merged_file_kept_on_disk(engine: Engine, store: Store, tmp_path: Path) -> None:
    music = tmp_path / "music"
    tagged_copy(music, "flac", name="numb.flac", artist="Phaeleh", title="Numb")
    tagged_copy(music, "mp3", name="numb.mp3", artist="Phaeleh", title="Numb")
    engine.apply(engine.plan_scan(music), assume_yes)

    engine.apply(engine.plan_merge(keep_files=True), assume_yes)

    assert len(store.list_tracks()) == 1
    rescan = engine.plan_scan(music)
    assert rescan.empty
    assert rescan.warnings == ()


def test_kept_track_link_untouched(engine: Engine, store: Store, tmp_path: Path) -> None:
    music = tmp_path / "music"
    flac = tagged_copy(music, "flac", name="numb.flac", artist="Phaeleh", title="Numb")
    mp3 = tagged_copy(music, "mp3", name="numb.mp3", artist="Phaeleh", title="Numb")
    beets = BeetsDatabase(tmp_path / "beets" / "library.db")
    own = beets.add_item(str(flac), artist="Phaeleh", title="Numb", label="Own")
    beets.add_item(str(mp3), artist="Phaeleh", title="Numb", label="Other")
    engine.apply(engine.plan_import(BEETS, beets.path), assume_yes)
    engine.apply(engine.plan_merge(keep_files=True), assume_yes)

    plan = engine.plan_import(BEETS, beets.path)

    assert plan.empty, plan.warnings
    (track,) = store.list_tracks()
    assert (track.path, track.label) == (normalize_path(str(flac)), "Own")
    assert track.unmapped["beets"]["id"] == own  # type: ignore[index]
