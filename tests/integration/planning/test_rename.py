import dataclasses
import datetime
from collections.abc import Callable
from pathlib import Path

import pytest

from support.audio import tagged_copy
from tunedex.model.cue import Cue, CueKind
from tunedex.model.paths import normalize_path
from tunedex.model.playlist import Playlist
from tunedex.planning import ApplyFailedError, Engine, PlanError, StaleTargetError, assume_yes
from tunedex.planning import engine as engine_module
from tunedex.planning.render import render_text
from tunedex.snapshots import SnapshotStore
from tunedex.store import Store


@pytest.fixture
def music(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    tagged_copy(
        root, "mp3", "sam_paganini-galaxy_www.slider.kz.mp3", artist="Sam Paganini", title="Galaxy"
    )
    tagged_copy(root, "flac", "02 glue.flac", artist="Bicep", title="Glue", remixer="Scuba")
    tagged_copy(root / "sub", "wav", "untitled.wav", title="Only a title")
    return root


def norm(path: Path) -> str:
    return normalize_path(str(path))


def scanned(engine: Engine, folder: Path) -> None:
    engine.apply(engine.plan_scan(folder), assume_yes)


def names(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def test_default_pattern_plans_and_renames_nothing(engine: Engine, music: Path) -> None:
    scanned(engine, music)
    before = names(music)

    plan = engine.plan_rename()

    assert plan.target == "renames"
    assert [(t.change, t.old_path, t.path) for t in plan.tracks] == [
        ("moved", norm(music / "02 glue.flac"), norm(music / "Bicep - Glue.flac")),
        (
            "moved",
            norm(music / "sam_paganini-galaxy_www.slider.kz.mp3"),
            norm(music / "Sam Paganini - Galaxy.mp3"),
        ),
    ]
    assert any("untitled.wav: not renamed, it has no artist" in w for w in plan.warnings)
    assert names(music) == before
    assert "sam_paganini-galaxy_www.slider.kz.mp3 → " in render_text(plan)


def test_pattern_and_scope(engine: Engine, music: Path) -> None:
    scanned(engine, music)
    plan = engine.plan_rename("{title}{ (remixer remix)}", under=music / "sub")
    assert [t.path for t in plan.tracks] == [norm(music / "sub" / "Only a title.wav")]
    plan = engine.plan_rename("{artist} - {title}{ (remixer remix)}")
    assert norm(music / "Bicep - Glue (Scuba remix).flac") in [t.path for t in plan.tracks]


def test_unknown_field_fails_before_planning(engine: Engine) -> None:
    with pytest.raises(PlanError, match="unknown field 'name'"):
        engine.plan_rename("{artist} - {name}")


def test_a_taken_name_is_skipped(engine: Engine, music: Path) -> None:
    scanned(engine, music)
    (music / "bicep - glue.FLAC").write_bytes(b"other")
    plan = engine.plan_rename()
    assert norm(music / "Bicep - Glue.flac") not in [t.path for t in plan.tracks]
    (warning,) = [w for w in plan.warnings if "already has that name" in w]
    assert "02 glue.flac" in warning
    assert "bicep - glue.FLAC" in warning


def test_two_tracks_with_one_name_are_both_skipped(
    engine: Engine, store: Store, music: Path
) -> None:
    tagged_copy(music, "mp3", "other.mp3", artist="Sam Paganini", title="Galaxy")
    scanned(engine, music)
    plan = engine.plan_rename()
    assert [t.path for t in plan.tracks] == [norm(music / "Bicep - Glue.flac")]
    (warning,) = [w for w in plan.warnings if "would all be named" in w]
    assert "other.mp3" in warning
    assert "sam_paganini-galaxy_www.slider.kz.mp3" in warning


def test_missing_files_are_skipped(engine: Engine, music: Path) -> None:
    scanned(engine, music)
    (music / "02 glue.flac").unlink()
    plan = engine.plan_rename()
    assert len(plan.tracks) == 1
    assert any("02 glue.flac: not renamed, the file is missing" in w for w in plan.warnings)


def test_apply_keeps_the_tracks_and_a_rescan_finds_nothing(
    engine: Engine, store: Store, snapshots: SnapshotStore, music: Path
) -> None:
    scanned(engine, music)
    track = store.find_track_by_path(str(music / "02 glue.flac"))
    assert track is not None
    cue = Cue(kind=CueKind.HOT, start_us=1_000, slot=0)
    store.update_track(dataclasses.replace(track, cues=(cue,)))
    store.add_node(Playlist(name="Peak", entries=(track.id,)))

    result = engine.apply(engine.plan_rename(), assume_yes)

    assert (result.status, result.files_renamed) == ("applied", 2)
    assert names(music) == [
        "Bicep - Glue.flac",
        "Sam Paganini - Galaxy.mp3",
        "sub/untitled.wav",
    ]
    renamed = store.get_track(track.id)
    assert renamed.path == norm(music / "Bicep - Glue.flac")
    assert (renamed.title, renamed.cues) == ("Glue", (cue,))
    (peak,) = store.load_library().playlists
    assert isinstance(peak, Playlist)
    assert peak.entries == (track.id,)
    assert engine.plan_scan(music).empty
    (snapshot,) = snapshots.list("renames")
    assert snapshot.id == result.snapshot
    assert {(Path(r.old).name, Path(r.new).name) for r in snapshot.renames} == {
        ("02 glue.flac", "Bicep - Glue.flac"),
        ("sam_paganini-galaxy_www.slider.kz.mp3", "Sam Paganini - Galaxy.mp3"),
    }


def test_a_case_only_change(engine: Engine, store: Store, tmp_path: Path) -> None:
    path = tagged_copy(tmp_path / "m", "mp3", "bicep - glue.mp3", artist="Bicep", title="Glue")
    scanned(engine, tmp_path / "m")
    plan = engine.plan_rename()
    assert [t.path for t in plan.tracks] == [norm(path.with_name("Bicep - Glue.mp3"))]
    engine.apply(plan, assume_yes)
    assert names(tmp_path / "m") == ["Bicep - Glue.mp3"]


def test_a_failure_halfway_renames_back(
    make_engine: Callable[..., Engine],
    store: Store,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "m"
    for index in range(5):
        tagged_copy(folder, "mp3", f"{index}.mp3", artist="A", title=f"T{index}")
    engine = make_engine()
    scanned(engine, folder)
    before, revision = names(folder), store.revision()
    calls: list[Path] = []
    real = engine_module.move_file

    def failing(old: Path, new: Path) -> None:
        calls.append(old)
        if len(calls) == 3:
            raise OSError(f"{old}: permission denied")
        real(old, new)

    monkeypatch.setattr(engine_module, "move_file", failing)
    with pytest.raises(ApplyFailedError, match=r"2\.mp3") as raised:
        engine.apply(engine.plan_rename(), assume_yes)

    assert raised.value.restored
    assert names(folder) == before
    assert store.revision() == revision


def test_a_name_taken_after_planning_stops_the_apply(engine: Engine, music: Path) -> None:
    scanned(engine, music)
    plan = engine.plan_rename()
    (music / "Bicep - Glue.flac").write_bytes(b"new")
    with pytest.raises(StaleTargetError, match=r"Bicep - Glue\.flac"):
        engine.apply(plan, assume_yes)
    assert (music / "sam_paganini-galaxy_www.slider.kz.mp3").exists()


def test_other_apps_are_warned(engine: Engine, store: Store, music: Path) -> None:
    scanned(engine, music)
    track = store.find_track_by_path(str(music / "02 glue.flac"))
    assert track is not None
    now = datetime.datetime(2026, 10, 31, tzinfo=datetime.UTC)
    store.record_sync("mixxx-0123456789ab", {}, now, source_values={track.id: {}})
    plan = engine.plan_rename()
    (warning,) = [w for w in plan.warnings if "mixxx" in w]
    assert warning.startswith(
        "the Mixxx database mixxx-0123456789ab still refers to the old names of 1"
    )
