import dataclasses
import datetime
from pathlib import Path

import pytest

from djlib.adapters.mixxx import MixxxAdapter
from djlib.model.cue import CueKind
from djlib.model.playlist import Folder, Playlist
from djlib.model.track import Track
from djlib.planning import Engine, StaleTargetError, assume_yes, render_text, to_json
from djlib.planning.selection import target_name
from djlib.snapshots import SnapshotStore
from djlib.store import Store
from support.audio import tagged_copy
from support.files import tree_bytes
from support.mixxx import HOT_CUE, MixxxDatabase, beat_grid

MIXXX = MixxxAdapter()
NOW = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.UTC)


@pytest.fixture
def mixxx(tmp_path: Path) -> MixxxDatabase:
    return MixxxDatabase(tmp_path / "profile" / "mixxxdb.sqlite")


def import_now(engine: Engine, database: MixxxDatabase) -> None:
    database.db.commit()
    result = engine.apply(engine.plan_import(MIXXX, database.path), assume_yes)
    assert result.status in {"applied", "nothing"}


def node_at(store: Store, *path: str) -> object:
    nodes = store.children()
    node = None
    for name in path:
        (node,) = [n for n in nodes if n.name == name]
        nodes = node.children if isinstance(node, Folder) else ()
    return node


def set_column(database: MixxxDatabase, column: str, value: object, track: int = 1) -> None:
    database.db.execute(f"UPDATE library SET {column} = ? WHERE id = ?", (value, track))
    database.db.commit()


# Planning and matching


def test_planned_import_changes_nothing(
    engine: Engine, store: Store, mixxx: MixxxDatabase, tmp_path: Path
) -> None:
    mixxx.add_track("/music/a.mp3", title="A")
    mixxx.close()
    revision, before = store.revision(), store.load_library()
    mixxx_files = tree_bytes(tmp_path / "profile")

    plan = engine.plan_import(MIXXX, mixxx.path)

    assert [t.change for t in plan.tracks] == ["added"]
    assert (store.revision(), store.load_library()) == (revision, before)
    assert tree_bytes(tmp_path / "profile") == mixxx_files


def test_scanned_track_enriched(
    engine: Engine, store: Store, mixxx: MixxxDatabase, tmp_path: Path
) -> None:
    music = tmp_path / "music"
    tagged_copy(music, "mp3", name="a.mp3", title="A")
    engine.apply(engine.plan_scan(music), assume_yes)
    (scanned,) = store.list_tracks()
    track = mixxx.add_track(scanned.path, title="A", bpm=128.0)
    mixxx.add_cue(track, HOT_CUE, 2 * 44100 * 2, hotcue=0)
    mixxx.set_beats(track, beat_grid(128.0, 0))

    import_now(engine, mixxx)

    (enriched,) = store.list_tracks()
    assert enriched.id == scanned.id
    assert enriched.bpm == 128.0
    assert [c.kind for c in enriched.cues] == [CueKind.HOT]
    assert enriched.beatgrid is not None


def test_first_import_fills_only_empty_fields(
    engine: Engine, store: Store, mixxx: MixxxDatabase
) -> None:
    store.add_track(dataclasses.replace(_track("/music/a.mp3"), title="Glue"))
    mixxx.add_track("/music/a.mp3", title="Glue (Edit)", bpm=127.0)

    plan = engine.plan_import(MIXXX, mixxx.path)
    engine.apply(plan, assume_yes)

    (track,) = store.list_tracks()
    assert (track.title, track.bpm) == ("Glue", 127.0)
    assert plan.conflicts == ()


def test_change_in_the_source_taken(engine: Engine, store: Store, mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3", bpm=127.0)
    import_now(engine, mixxx)
    set_column(mixxx, "bpm", 128.0)

    plan = engine.plan_import(MIXXX, mixxx.path)
    engine.apply(plan, assume_yes)

    (change,) = plan.tracks
    assert [(f.field, f.before, f.after) for f in change.fields] == [("bpm", 127.0, 128.0)]
    assert store.list_tracks()[0].bpm == 128.0


def test_edited_on_both_sides(engine: Engine, store: Store, mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3", genre="Techno")
    import_now(engine, mixxx)
    (track,) = store.list_tracks()
    store.update_track(dataclasses.replace(track, genre="House"))
    set_column(mixxx, "genre", "Minimal")

    plan = engine.plan_import(MIXXX, mixxx.path)
    engine.apply(plan, assume_yes)

    assert [(c.field, c.library_value, c.file_value) for c in plan.conflicts] == [
        ("genre", "House", "Minimal")
    ]
    assert store.list_tracks()[0].genre == "House"
    assert engine.plan_import(MIXXX, mixxx.path).conflicts == ()


def test_tracks_only_in_djlib_untouched(engine: Engine, store: Store, mixxx: MixxxDatabase) -> None:
    mine = _track("/music/mine.mp3")
    store.add_track(mine)
    mixxx.add_track("/music/a.mp3")

    import_now(engine, mixxx)

    assert store.get_track(mine.id) == mine


def test_unmapped_follows_the_source(engine: Engine, store: Store, mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3", bpm_lock=0)
    import_now(engine, mixxx)
    set_column(mixxx, "bpm_lock", 1)

    plan = engine.plan_import(MIXXX, mixxx.path)
    engine.apply(plan, assume_yes)

    assert store.list_tracks()[0].unmapped["mixxx"]["bpm_lock"] is True  # type: ignore[index]
    assert plan.tracks == () and plan.rebased == 1


# The source folder


def test_playlists_under_the_source_folder(
    engine: Engine, store: Store, mixxx: MixxxDatabase
) -> None:
    a = mixxx.add_track("/music/a.mp3")
    mixxx.add_playlist("Peak", [a])
    mixxx.add_crate("Techno", [a])
    store.add_node(Playlist(name="Mine"))

    plan = engine.plan_import(MIXXX, mixxx.path)
    engine.apply(plan, assume_yes)

    assert [n.name for n in store.children()] == ["Mine", "Mixxx"]
    peak = node_at(store, "Mixxx", "Playlists", "Peak")
    assert isinstance(peak, Playlist) and len(peak.entries) == 1
    assert isinstance(node_at(store, "Mixxx", "Crates", "Techno"), Playlist)
    assert [(n.change, n.path) for n in plan.nodes] == [
        ("added", ("Mixxx",)),
        ("added", ("Mixxx", "Playlists")),
        ("added", ("Mixxx", "Playlists", "Peak")),
        ("added", ("Mixxx", "Crates")),
        ("added", ("Mixxx", "Crates", "Techno")),
    ]


def test_reimport_keeps_identifiers(engine: Engine, store: Store, mixxx: MixxxDatabase) -> None:
    a, b = mixxx.add_track("/music/a.mp3"), mixxx.add_track("/music/b.mp3")
    peak = mixxx.add_playlist("Peak", [a])
    import_now(engine, mixxx)
    before = node_at(store, "Mixxx", "Playlists", "Peak")
    mixxx.db.execute(
        "INSERT INTO PlaylistTracks (playlist_id, track_id, position) VALUES (?, ?, 2)", (peak, b)
    )
    mixxx.db.commit()

    plan = engine.plan_import(MIXXX, mixxx.path)
    engine.apply(plan, assume_yes)

    after = node_at(store, "Mixxx", "Playlists", "Peak")
    assert isinstance(before, Playlist) and isinstance(after, Playlist)
    assert after.id == before.id
    assert len(after.entries) == 2
    assert [(n.change, n.path, n.entries_added) for n in plan.nodes] == [
        ("updated", ("Mixxx", "Playlists", "Peak"), ("/music/b.mp3",))
    ]


def test_playlist_removed_in_the_source(engine: Engine, store: Store, mixxx: MixxxDatabase) -> None:
    a = mixxx.add_track("/music/a.mp3")
    old = mixxx.add_playlist("Old", [a])
    mixxx.add_playlist("Kept", [a])
    import_now(engine, mixxx)
    mixxx.db.execute("DELETE FROM PlaylistTracks WHERE playlist_id = ?", (old,))
    mixxx.db.execute("DELETE FROM Playlists WHERE id = ?", (old,))
    mixxx.db.commit()

    plan = engine.plan_import(MIXXX, mixxx.path)
    engine.apply(plan, assume_yes)

    assert [(n.change, n.path) for n in plan.nodes] == [("removed", ("Mixxx", "Playlists", "Old"))]
    assert "  - Mixxx/Playlists/Old (playlist)" in render_text(plan)
    assert to_json(plan)["playlists"][0]["change"] == "removed"  # type: ignore[index]
    playlists = node_at(store, "Mixxx", "Playlists")
    assert isinstance(playlists, Folder) and [c.name for c in playlists.children] == ["Kept"]


def test_folder_recreated_after_deletion(
    engine: Engine, store: Store, mixxx: MixxxDatabase
) -> None:
    mixxx.add_playlist("Peak", [mixxx.add_track("/music/a.mp3")])
    import_now(engine, mixxx)
    store.delete_node(store.children()[0].id)

    import_now(engine, mixxx)

    assert isinstance(node_at(store, "Mixxx", "Playlists", "Peak"), Playlist)


def test_two_mixxx_databases(engine: Engine, store: Store, tmp_path: Path) -> None:
    first = MixxxDatabase(tmp_path / "one" / "mixxxdb.sqlite")
    first.add_playlist("One", [first.add_track("/music/a.mp3")])
    second = MixxxDatabase(tmp_path / "two" / "mixxxdb.sqlite")
    second.add_playlist("Two", [second.add_track("/music/b.mp3")])
    import_now(engine, first)
    import_now(engine, second)
    two_before = node_at(store, "Mixxx (2)")

    first.add_playlist("More", [1])
    import_now(engine, first)

    assert [n.name for n in store.children()] == ["Mixxx", "Mixxx (2)"]
    assert node_at(store, "Mixxx (2)") == two_before
    assert isinstance(node_at(store, "Mixxx", "Playlists", "More"), Playlist)


# Applying


def test_applied_with_snapshot_and_reimport_is_empty(
    engine: Engine, snapshots: SnapshotStore, mixxx: MixxxDatabase
) -> None:
    a = mixxx.add_track("/music/a.mp3", title="A", bpm=120.0)
    mixxx.add_cue(a, HOT_CUE, 44100 * 2, hotcue=0)
    mixxx.set_beats(a, beat_grid(120.0, 0))
    mixxx.add_playlist("Peak", [a])
    mixxx.add_crate("Techno", [a])

    result = engine.apply(engine.plan_import(MIXXX, mixxx.path), assume_yes)

    assert result.status == "applied"
    assert [s.id for s in snapshots.list("library")] == [result.snapshot]
    assert engine.plan_import(MIXXX, mixxx.path).empty


def test_library_changed_after_planning(engine: Engine, store: Store, mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3")
    plan = engine.plan_import(MIXXX, mixxx.path)
    store.add_track(_track("/music/other.mp3"))

    with pytest.raises(StaleTargetError):
        engine.apply(plan, assume_yes)


def _track(path: str) -> Track:
    return Track(path_origin=path)


# Playlists djlib exported there


def _exported(store: Store, mixxx: MixxxDatabase) -> Playlist:
    a = mixxx.add_track("/music/a.mp3")
    mixxx.add_playlist("Techno / Peak", [a])
    peak = Playlist(name="Peak")
    store.add_node(Folder(name="Techno", children=(peak,)))
    source = target_name(MIXXX.name, mixxx.path)
    store.record_sync(
        source, {peak.id: "0" * 64}, NOW, target_paths={peak.id: ("Playlists", "Techno / Peak")}
    )
    return peak


def test_own_playlist_round_trip(engine: Engine, store: Store, mixxx: MixxxDatabase) -> None:
    _exported(store, mixxx)

    import_now(engine, mixxx)

    playlists = node_at(store, "Mixxx", "Playlists")
    assert isinstance(playlists, Folder) and playlists.children == ()


def test_owner_deleted(engine: Engine, store: Store, mixxx: MixxxDatabase) -> None:
    peak = _exported(store, mixxx)
    store.delete_node(peak.id)

    plan = engine.plan_import(MIXXX, mixxx.path)

    assert ("added", ("Mixxx", "Playlists", "Techno / Peak")) in [
        (n.change, n.path) for n in plan.nodes
    ]
