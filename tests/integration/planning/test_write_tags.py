import dataclasses
import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from mutagen import id3

from support.audio import CLIPS, tagged_copy
from support.files import sha256
from tunedex.model.cue import Cue, CueKind
from tunedex.model.key import Key, Mode
from tunedex.model.track import Track
from tunedex.planning import ApplyFailedError, Engine, StaleTargetError, assume_yes, to_json
from tunedex.planning.render import render_text
from tunedex.snapshots import SnapshotStore
from tunedex.sources.tags import read_file
from tunedex.store import Store
from tunedex.tagwrite.writer import write_tags


@pytest.fixture
def music(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    shutil.copytree(CLIPS, root, ignore=shutil.ignore_patterns("*.py", "*.sh", "*.md", "silence.*"))
    return root


def scanned(engine: Engine, folder: Path) -> None:
    engine.apply(engine.plan_scan(folder), assume_yes)


def edit(store: Store, path: Path, **values: object) -> None:
    track = store.find_track_by_path(str(path))
    assert track is not None
    store.update_track(dataclasses.replace(track, **values))


def test_nothing_to_write_after_a_scan(engine: Engine, music: Path) -> None:
    scanned(engine, music)
    plan = engine.plan_write_tags()
    assert plan.empty
    assert plan.target == "tags"


def test_cleaned_title_is_planned_and_nothing_written(
    engine: Engine, store: Store, music: Path, tmp_path: Path
) -> None:
    scanned(engine, music)
    path = music / "tagged-v24.mp3"
    edit(store, path, title="Galaxy", comment=None)
    before = sha256(path)

    plan = engine.plan_write_tags()

    (change,) = plan.tags
    assert change.path == str(path)
    assert [(f.field, f.before, f.after) for f in change.fields] == [
        ("title", "Galaxy [www.slider.kz]", "Galaxy"),
        ("comment", "first release", None),
    ]
    (file,) = plan.action.files  # pyright: ignore[reportAttributeAccessIssue]
    assert file.fields == {"title": "Galaxy", "comment": None}
    assert plan.snapshot_bytes == file.tag_bytes > 0
    assert sha256(path) == before
    assert not (tmp_path / "snapshots" / "tags").exists()
    text = render_text(plan)
    assert "Files to write: 1" in text
    assert "title: 'Galaxy [www.slider.kz]' → 'Galaxy'" in text
    document = to_json(plan)
    assert document["target"] == "tags"
    assert document["tags"] == [
        {
            "track_id": str(change.track_id),
            "path": str(path),
            "name": "Sam Paganini - Galaxy",
            "fields": [
                {
                    "field": "title",
                    "before": "Galaxy [www.slider.kz]",
                    "after": "Galaxy",
                    "by": None,
                },
                {"field": "comment", "before": "first release", "after": None, "by": None},
            ],
        }
    ]
    assert document["snapshot_bytes"] == file.tag_bytes


def test_under_limits_the_plan(engine: Engine, store: Store, music: Path) -> None:
    scanned(engine, music)
    (music / "sub").mkdir()
    for name in ("tagged.flac", "tagged.wav"):
        edit(store, music / name, title="New")
    plan = engine.plan_write_tags(under=music / "sub")
    assert plan.empty
    plan = engine.plan_write_tags(under=music)
    assert len(plan.tags) == 2


def test_files_edited_elsewhere_are_skipped(engine: Engine, store: Store, music: Path) -> None:
    scanned(engine, music)
    path = music / "tagged.flac"
    edit(store, path, title="Galaxy")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    plan = engine.plan_write_tags()

    assert plan.empty
    assert any("changed since the last scan" in w and "scan first" in w for w in plan.warnings)


def test_missing_and_unsupported_files_are_skipped(
    engine: Engine, store: Store, music: Path
) -> None:
    scanned(engine, music)
    edit(store, music / "tagged.m4a", title="Galaxy")
    edit(store, music / "tagged.wav", title="Galaxy")
    (music / "tagged.wav").unlink()

    plan = engine.plan_write_tags()

    assert plan.empty
    assert any("M4A files are not written yet" in w for w in plan.warnings)
    assert any("missing" in w and "tagged.wav" in w for w in plan.warnings)


def test_v24_frames_that_would_be_dropped_are_warned(
    engine: Engine, store: Store, music: Path
) -> None:
    scanned(engine, music)
    edit(store, music / "tagged-v24.mp3", title="Galaxy")
    plan = engine.plan_write_tags()
    assert any("TSOP" in w for w in plan.warnings)


def test_written_tags_keep_art_cues_stay_and_a_rescan_is_empty(
    engine: Engine, store: Store, snapshots: SnapshotStore, music: Path
) -> None:
    scanned(engine, music)
    cue = Cue(kind=CueKind.HOT, start_us=1_000, slot=0)
    for name in ("tagged-v24.mp3", "tagged.flac", "tagged.wav", "tagged.aiff"):
        edit(store, music / name, title="Galaxy", bpm=127.5, rating=5, cues=(cue,))
    paths = [music / n for n in ("tagged-v24.mp3", "tagged.flac", "tagged.wav", "tagged.aiff")]
    before = {p: sha256(p) for p in paths}
    tracks_before = store.list_tracks()

    result = engine.apply(engine.plan_write_tags(), assume_yes)

    assert (result.status, result.files_written) == ("applied", 4)
    for path in paths:
        values = read_file(path).values
        assert (values["title"], values["bpm"]) == ("Galaxy", 127.5)
        assert "rating" not in values
    assert id3.ID3(music / "tagged-v24.mp3")["APIC:"].data
    assert store.list_tracks() == tracks_before
    assert engine.plan_scan(music).empty
    assert engine.plan_write_tags().empty

    (snapshot,) = snapshots.list("tags")
    assert snapshot.id == result.snapshot
    snapshots.restore(snapshot)
    assert {p: sha256(p) for p in paths} == before


def test_a_failure_halfway_restores_the_written_files(
    make_engine: Callable[..., Engine], store: Store, music: Path
) -> None:
    engine = make_engine()
    scanned(engine, music)
    names = ["tagged-ape.mp3", "tagged-v23-v1.mp3", "tagged-v24.mp3", "tagged.aiff", "tagged.flac"]
    for name in names:
        edit(store, music / name, title="Galaxy")
    before = {n: sha256(music / n) for n in names}
    mtimes = {n: (music / n).stat().st_mtime_ns for n in names}
    calls: list[Path] = []

    def failing(path: Path, fields: Mapping[str, str | None]) -> None:
        calls.append(path)
        if len(calls) == 3:
            raise OSError(f"{path}: disk full")
        write_tags(path, fields)

    engine = make_engine(_write_tags=failing)
    revision = store.revision()
    with pytest.raises(ApplyFailedError, match="tagged-v24") as raised:
        engine.apply(engine.plan_write_tags(), assume_yes)

    assert raised.value.restored
    assert {n: sha256(music / n) for n in names} == before
    assert (music / names[3]).stat().st_mtime_ns == mtimes[names[3]]
    assert (music / names[4]).stat().st_mtime_ns == mtimes[names[4]]
    assert store.revision() == revision


def test_a_file_changed_after_planning_stops_the_apply(
    engine: Engine, store: Store, music: Path
) -> None:
    scanned(engine, music)
    edit(store, music / "tagged.flac", title="Galaxy")
    plan = engine.plan_write_tags()
    path = music / "tagged.flac"
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    with pytest.raises(StaleTargetError, match="changed since the plan"):
        engine.apply(plan, assume_yes)


def test_a_library_changed_after_planning_stops_the_apply(
    engine: Engine, store: Store, music: Path
) -> None:
    scanned(engine, music)
    edit(store, music / "tagged.flac", title="Galaxy")
    plan = engine.plan_write_tags()
    edit(store, music / "tagged.flac", title="Other")
    with pytest.raises(StaleTargetError):
        engine.apply(plan, assume_yes)


def test_unscanned_tracks_are_skipped(engine: Engine, store: Store, tmp_path: Path) -> None:
    path = tagged_copy(tmp_path, "mp3", title="Old")
    store.add_track(Track(path_origin=str(path), title="New"))
    plan = engine.plan_write_tags()
    assert plan.empty
    assert any("never scanned" in w for w in plan.warnings)


def test_keys_and_numbers(engine: Engine, store: Store, tmp_path: Path) -> None:
    path = tagged_copy(tmp_path / "m", "mp3", title="T", key="1m", bpm="128", track="3/12")
    scanned(engine, tmp_path / "m")
    edit(store, path, key=Key(tonic=9, mode=Mode.MINOR), bpm=128.0, track_number=3)
    assert engine.plan_write_tags().empty  # 1m is A minor: nothing to write
    edit(store, path, key=Key(tonic=0, mode=Mode.MINOR), key_original=None, track_number=4)
    engine.apply(engine.plan_write_tags(), assume_yes)
    tags = id3.ID3(path)
    assert (str(tags["TKEY"]), str(tags["TRCK"]), str(tags["TBPM"])) == ("Cm", "4/12", "128")


def test_undoing_a_write_keeps_the_library_values(
    engine: Engine, store: Store, snapshots: SnapshotStore, music: Path
) -> None:
    scanned(engine, music)
    path = music / "tagged.flac"
    edit(store, path, title="Galaxy")
    engine.apply(engine.plan_write_tags(), assume_yes)
    (snapshot,) = snapshots.list("tags")

    snapshots.restore(snapshot)
    engine.apply(engine.plan_scan(music), assume_yes)

    track = store.find_track_by_path(str(path))
    assert track is not None
    assert track.title == "Galaxy"  # the file's old title did not come back
    assert [t.path for t in engine.plan_write_tags().tags] == [str(path)]


def test_a_file_edited_elsewhere_after_writing_is_read_on_the_next_scan(
    engine: Engine, store: Store, music: Path
) -> None:
    scanned(engine, music)
    path = music / "tagged.flac"
    edit(store, path, title="Galaxy")
    engine.apply(engine.plan_write_tags(), assume_yes)
    write_tags(path, {"album": "Remixes"})  # another program

    engine.apply(engine.plan_scan(music), assume_yes)

    track = store.find_track_by_path(str(path))
    assert track is not None
    assert (track.title, track.album) == ("Galaxy", "Remixes")
