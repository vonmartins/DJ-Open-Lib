"""Planning and applying fixes (specs/rules-engine, plan-apply)."""

import dataclasses
from pathlib import Path

from djlib.model.track import Track
from djlib.planning import Engine, assume_yes, render_text, to_json
from djlib.rules.ruleset import defaults
from djlib.store import Store
from support.audio import tagged_copy


def test_fix_named(engine: Engine, store: Store) -> None:
    store.add_track(Track(path_origin="/music/a.mp3", artist="A", title="Glue (freebeats.com)"))

    plan = engine.plan_fix(defaults())

    (change,) = plan.tracks
    (field,) = change.fields
    assert (field.field, field.after, field.by) == ("title", "Glue", "remove_urls")
    assert "title: 'Glue (freebeats.com)' → 'Glue'  (remove_urls)" in render_text(plan)
    assert to_json(plan)["tracks"][0]["fields"][0]["by"] == "remove_urls"  # type: ignore[index]


def test_planned_fix_changes_nothing_then_applies(engine: Engine, store: Store) -> None:
    track = Track(path_origin="/music/a.mp3", artist="Echo Unit", title="Storm (feat. Mira)")
    store.add_track(track)
    revision, before = store.revision(), store.load_library()

    plan = engine.plan_fix(defaults())

    assert (store.revision(), store.load_library()) == (revision, before)
    engine.apply(plan, assume_yes)
    fixed = store.get_track(track.id)
    assert (fixed.title, fixed.artist) == ("Storm", "Echo Unit feat. Mira")
    assert engine.plan_fix(defaults()).empty


def test_scan_keeps_fixed_values(engine: Engine, store: Store, tmp_path: Path) -> None:
    music = tmp_path / "music"
    tagged_copy(music, "mp3", name="a.mp3", title="Glue_Edit")
    engine.apply(engine.plan_scan(music), assume_yes)

    engine.apply(engine.plan_fix(defaults()), assume_yes)
    (track,) = store.list_tracks()
    assert track.title == "Glue Edit"

    rescan = engine.plan_scan(music)
    engine.apply(rescan, assume_yes)
    assert store.list_tracks()[0].title == "Glue Edit"
    assert rescan.conflicts == ()


def test_nothing_to_fix(engine: Engine, store: Store) -> None:
    store.add_track(Track(path_origin="/music/a.mp3", artist="Bicep", title="Glue"))

    assert engine.plan_fix(defaults()).empty
    assert dataclasses.replace(defaults(), fixes=()).rules == ()


def test_fix_under_a_folder(engine: Engine, store: Store) -> None:
    store.add_track(Track(path_origin="/music/new/a.mp3", title="Glue (freebeats.com)"))
    store.add_track(Track(path_origin="/music/old/b.mp3", title="Rise (freebeats.com)"))

    plan = engine.plan_fix(defaults(), under="/music/new")

    assert [c.path for c in plan.tracks] == ["/music/new/a.mp3"]
