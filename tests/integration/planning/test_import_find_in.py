"""Importing only the tracks whose files are under a search folder (specs/library-import)."""

from pathlib import Path

from support.audio import tagged_copy
from support.beets import BeetsDatabase
from support.mixxx import MixxxDatabase
from tunedex.adapters.mixxx import MixxxAdapter
from tunedex.model.paths import normalize_path
from tunedex.model.playlist import Folder, Playlist
from tunedex.planning import Engine, assume_yes
from tunedex.sources.beets import BeetsSource
from tunedex.store import Store

BEETS = BeetsSource()


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_only_local_copies_imported(engine: Engine, store: Store, tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "library.db")
    beets.add_item("/mnt/server/Calyx/a.mp3", title="A")
    beets.add_item("/mnt/server/Phace/b.mp3", title="B")
    a = touch(tmp_path / "Artists" / "Calyx" / "a.mp3")

    plan = engine.plan_import(BEETS, beets.path, find_in=tmp_path / "Artists")
    engine.apply(plan, assume_yes)

    assert [(t.change, t.path) for t in plan.tracks] == [("added", normalize_path(str(a)))]
    (warning,) = [w for w in plan.warnings if "not imported" in w]
    assert warning.startswith("1 source tracks are not under") and "Phace/b.mp3" in warning
    assert [t.path for t in store.list_tracks()] == [normalize_path(str(a))]


def test_more_copied_later(engine: Engine, store: Store, tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "library.db")
    beets.add_item("/mnt/server/Calyx/a.mp3", title="A")
    beets.add_item("/mnt/server/Phace/b.mp3", title="B")
    artists = tmp_path / "Artists"
    touch(artists / "Calyx" / "a.mp3")
    engine.apply(engine.plan_import(BEETS, beets.path, find_in=artists), assume_yes)
    (first,) = store.list_tracks()
    b = touch(artists / "Phace" / "b.mp3")

    plan = engine.plan_import(BEETS, beets.path, find_in=artists)
    engine.apply(plan, assume_yes)

    assert [(t.change, t.path) for t in plan.tracks] == [("added", normalize_path(str(b)))]
    assert store.get_track(first.id) == first
    assert engine.plan_import(BEETS, beets.path, find_in=artists).empty


def test_scanned_copy_matched(engine: Engine, store: Store, tmp_path: Path) -> None:
    artists = tmp_path / "Artists"
    tagged_copy(artists / "Calyx", "mp3", name="a.mp3", title="A")
    engine.apply(engine.plan_scan(artists), assume_yes)
    (scanned,) = store.list_tracks()
    beets = BeetsDatabase(tmp_path / "library.db")
    beets.add_item("/mnt/server/Calyx/a.mp3", title="A", label="Label")

    plan = engine.plan_import(BEETS, beets.path, find_in=artists)
    engine.apply(plan, assume_yes)

    (track,) = store.list_tracks()
    assert (track.id, track.label) == (scanned.id, "Label")
    assert [t.change for t in plan.tracks] == ["updated"]


def test_playlist_entry_left_out(engine: Engine, store: Store, tmp_path: Path) -> None:
    mixxx = MixxxDatabase(tmp_path / "profile" / "mixxxdb.sqlite")
    here = mixxx.add_track("/mnt/server/Calyx/a.mp3")
    gone = mixxx.add_track("/mnt/server/Phace/b.mp3")
    mixxx.add_playlist("Peak", [here, gone])
    mixxx.close()
    touch(tmp_path / "Artists" / "Calyx" / "a.mp3")

    engine.apply(
        engine.plan_import(MixxxAdapter(), mixxx.path, find_in=tmp_path / "Artists"), assume_yes
    )

    (root,) = store.children()
    assert isinstance(root, Folder)
    (playlists, _crates) = root.children
    assert isinstance(playlists, Folder)
    (peak,) = playlists.children
    assert isinstance(peak, Playlist) and len(peak.entries) == 1
