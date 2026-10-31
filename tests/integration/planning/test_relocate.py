"""Relocating tracks whose files are not on this computer (specs/track-relocation)."""

import datetime
import os
import sys
from pathlib import Path

import pytest

from tunedex.model.paths import normalize_path
from tunedex.model.track import Track
from tunedex.planning import Engine, PlanError, assume_yes
from tunedex.store import FileState, Store

NOW = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.UTC)


def touch(path: Path, size: int = 10) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def add(store: Store, path: str, **fields: object) -> Track:
    track = Track(path_origin=path, **fields)  # type: ignore[arg-type]
    store.add_track(track)
    return track


def moves(engine: Engine, folder: Path) -> dict[str, str]:
    plan = engine.plan_relocate(folder)
    return {t.old_path: t.path for t in plan.tracks if t.old_path is not None}


def test_existing_files_untouched(engine: Engine, store: Store, tmp_path: Path) -> None:
    here = touch(tmp_path / "here" / "a.mp3")
    add(store, str(here))
    add(store, "/gone/b.mp3")
    touch(tmp_path / "music" / "a.mp3")
    b = touch(tmp_path / "music" / "b.mp3")

    assert moves(engine, tmp_path / "music") == {"/gone/b.mp3": normalize_path(str(b))}


def test_same_tail(engine: Engine, store: Store, tmp_path: Path) -> None:
    add(store, "/mnt/Elements/Music/Calyx/x.mp3")
    right = touch(tmp_path / "Music" / "Calyx" / "x.mp3")
    touch(tmp_path / "Other" / "x.mp3")

    assert moves(engine, tmp_path) == {
        "/mnt/Elements/Music/Calyx/x.mp3": normalize_path(str(right))
    }


def test_ambiguous(engine: Engine, store: Store, tmp_path: Path) -> None:
    add(store, "/old/x.mp3")
    touch(tmp_path / "a" / "x.mp3")
    touch(tmp_path / "b" / "x.mp3")

    plan = engine.plan_relocate(tmp_path)

    assert plan.empty
    (warning,) = plan.warnings
    assert warning.startswith("1 missing tracks match several files") and "/old/x.mp3" in warning


def test_size_settles_a_tie(engine: Engine, store: Store, tmp_path: Path) -> None:
    track = add(store, "/old/x.mp3")
    store._put_file_state(  # pyright: ignore[reportPrivateUsage]
        FileState(track_id=track.id, size=20, mtime_ns=1, quick_hash="0" * 64, scanned_at=NOW)
    )
    touch(tmp_path / "a" / "x.mp3", size=10)
    right = touch(tmp_path / "b" / "x.mp3", size=20)

    assert moves(engine, tmp_path) == {"/old/x.mp3": normalize_path(str(right))}


def test_case_differs(engine: Engine, store: Store, tmp_path: Path) -> None:
    add(store, "/old/Track.MP3")
    file = touch(tmp_path / "track.mp3")

    assert moves(engine, tmp_path) == {"/old/Track.MP3": normalize_path(str(file))}


def test_file_already_in_the_library(engine: Engine, store: Store, tmp_path: Path) -> None:
    file = touch(tmp_path / "x.mp3")
    add(store, str(file))
    add(store, "/old/x.mp3")

    plan = engine.plan_relocate(tmp_path)

    assert plan.empty
    assert plan.warnings[0].startswith("1 missing tracks were not found")


def test_one_file_claimed_twice(engine: Engine, store: Store, tmp_path: Path) -> None:
    add(store, "/old/a/x.mp3")
    add(store, "/old/b/x.mp3")
    touch(tmp_path / "x.mp3")

    plan = engine.plan_relocate(tmp_path)

    assert plan.empty
    assert plan.warnings[0].startswith("2 missing tracks match several files")


def test_planned_relocation_changes_nothing(engine: Engine, store: Store, tmp_path: Path) -> None:
    track = add(store, "/old/x.mp3", title="X")
    file = touch(tmp_path / "x.mp3")
    revision, before = store.revision(), store.load_library()

    plan = engine.plan_relocate(tmp_path)

    assert (store.revision(), store.load_library()) == (revision, before)
    (change,) = plan.tracks
    assert (change.change, change.name, change.old_path, change.path, change.fields) == (
        "moved",
        "X",
        "/old/x.mp3",
        normalize_path(str(file)),
        (),
    )
    engine.apply(plan, assume_yes)
    assert store.get_track(track.id).path == normalize_path(str(file))


def test_nothing_missing(engine: Engine, store: Store, tmp_path: Path) -> None:
    add(store, str(touch(tmp_path / "x.mp3")))

    assert engine.plan_relocate(tmp_path).empty


def test_folder_must_exist(engine: Engine, tmp_path: Path) -> None:
    with pytest.raises(PlanError, match="not a folder"):
        engine.plan_relocate(tmp_path / "nowhere")


@pytest.mark.skipif(sys.platform != "linux", reason="non-UTF-8 names need a byte filesystem")
def test_non_utf8_name_skipped(engine: Engine, store: Store, tmp_path: Path) -> None:
    add(store, "/old/caf.mp3")
    (tmp_path / "x").mkdir()
    open(os.path.join(os.fsencode(tmp_path / "x"), b"caf\xe9.mp3"), "wb").close()  # noqa: PTH118, PTH123

    plan = engine.plan_relocate(tmp_path)

    assert plan.empty and any("not valid UTF-8" in w for w in plan.warnings)


def test_exact_name_wins(engine: Engine, store: Store, tmp_path: Path) -> None:
    add(store, "/old/Life On Earth.mp3")
    add(store, "/old/Life on Earth.mp3")
    upper = touch(tmp_path / "Life On Earth.mp3")
    lower = touch(tmp_path / "Life on Earth.mp3")
    if upper.samefile(lower):
        pytest.skip("case-insensitive filesystem")

    assert moves(engine, tmp_path) == {
        "/old/Life On Earth.mp3": normalize_path(str(upper)),
        "/old/Life on Earth.mp3": normalize_path(str(lower)),
    }
