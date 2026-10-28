"""Planning writes to Mixxx databases, checked by reading the planned content back."""

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from djlib.adapters.contract import WriteOptions, WritePlan
from djlib.adapters.errors import AdapterError
from djlib.adapters.mixxx import MixxxAdapter
from djlib.model.beatgrid import BeatGrid, BeatMarker
from djlib.model.cue import Cue, CueKind
from djlib.model.key import Key, Mode
from djlib.model.library import Library
from djlib.model.playlist import Folder, Playlist, Smartlist
from djlib.model.track import Track
from support.files import tree_bytes
from support.mixxx import HOT_CUE, INTRO, MixxxDatabase, beat_grid

ADAPTER = MixxxAdapter(running=lambda: False)


@pytest.fixture
def mixxx(tmp_path: Path) -> MixxxDatabase:
    return MixxxDatabase(tmp_path / "profile" / "mixxxdb.sqlite")


def read(path: Path) -> Library:
    return ADAPTER.read(path).library


def plan(library: Library, path: Path, **options: object) -> WritePlan:
    return ADAPTER.plan_write(library, path, WriteOptions(**options))  # type: ignore[arg-type]


def written(write_plan: WritePlan) -> None:
    """Do what applying does: replace the database with the planned content."""
    for change in write_plan.changes:
        change.path.write_bytes(change.content)


def rows(path: Path, query: str, *parameters: object) -> list[tuple[object, ...]]:
    with sqlite3.connect(path) as db:
        return db.execute(query, parameters).fetchall()


def by_path(library: Library, path: str) -> Track:
    (track,) = [t for t in library.tracks.values() if t.path == path]
    return track


def replaced(library: Library, path: str, **values: object) -> Library:
    track = by_path(library, path)
    tracks = dict(library.tracks)
    tracks[track.id] = dataclasses.replace(track, **values)  # type: ignore[arg-type]
    return dataclasses.replace(library, tracks=tracks)


def imported(path: Path) -> tuple[Library, Folder]:
    """What an import gives: the read library with its folders under one source folder."""
    library = read(path)
    root = Folder(name="Mixxx", children=library.playlists)
    return dataclasses.replace(library, playlists=(root,)), root


# The file


def test_planned_write_changes_nothing(mixxx: MixxxDatabase, tmp_path: Path) -> None:
    mixxx.add_track("/music/a.mp3", title="A")
    mixxx.close()
    library = replaced(read(mixxx.path), "/music/a.mp3", title="B")
    before = tree_bytes(tmp_path / "profile")

    write_plan = plan(library, mixxx.path)

    assert len(write_plan.changes) == 1
    assert tree_bytes(tmp_path / "profile") == before


def test_nothing_to_write(mixxx: MixxxDatabase) -> None:
    a = mixxx.add_track("/music/a.mp3", title="A", bpm=128.0, key_id=22, duration=300.0)
    mixxx.add_cue(a, HOT_CUE, 2_646_000, hotcue=0)
    mixxx.set_beats(a, beat_grid(128.0, 22050))
    mixxx.add_playlist("Peak", [a])
    mixxx.add_crate("Techno", [a])
    mixxx.close()
    library, root = imported(mixxx.path)

    write_plan = plan(library, mixxx.path, source_root=root.id)

    assert write_plan.changes == ()
    assert write_plan.losses == ()


def test_unmodelled_data_kept(mixxx: MixxxDatabase) -> None:
    a = mixxx.add_track(
        "/music/a.mp3", title="A", replaygain=0.5, coverart_hash=1234, beats_sub_version="x"
    )
    mixxx.add_cue(a, INTRO, 1000, length=5000)
    mixxx.close()
    write_plan = plan(replaced(read(mixxx.path), "/music/a.mp3", title="B"), mixxx.path)

    written(write_plan)

    assert rows(mixxx.path, "SELECT title, replaygain, coverart_hash FROM library") == [
        ("B", 0.5, 1234)
    ]
    assert rows(mixxx.path, "SELECT type, position, length FROM cues") == [(INTRO, 1000, 5000)]


def test_wrong_schema_version(tmp_path: Path) -> None:
    database = MixxxDatabase(tmp_path / "mixxxdb.sqlite", schema_version=40)
    database.close()

    with pytest.raises(AdapterError, match="schema version 39"):
        plan(Library(), database.path)


def test_mixxx_running(mixxx: MixxxDatabase) -> None:
    mixxx.close()
    adapter = MixxxAdapter(running=lambda: True)

    with pytest.raises(AdapterError, match="quit Mixxx"):
        adapter.plan_write(Library(), mixxx.path)


def test_journal_refused(mixxx: MixxxDatabase) -> None:
    mixxx.close()
    mixxx.path.with_name("mixxxdb.sqlite-journal").write_bytes(b"")

    with pytest.raises(AdapterError, match="journal"):
        plan(Library(), mixxx.path)


def test_check_runs_again(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3", title="A")
    mixxx.close()
    state = {"running": False}
    adapter = MixxxAdapter(running=lambda: state["running"])
    library = replaced(read(mixxx.path), "/music/a.mp3", title="B")
    write_plan = adapter.plan_write(library, mixxx.path)
    state["running"] = True

    assert write_plan.check is not None
    with pytest.raises(AdapterError, match="quit Mixxx"):
        write_plan.check()


# Track fields


def test_retitled_track(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3", title="A", timesplayed=7, duration=300.0)
    mixxx.close()
    library = replaced(
        read(mixxx.path), "/music/a.mp3", title="B", play_count=1, duration_us=1_000_000
    )

    written(plan(library, mixxx.path))

    assert rows(mixxx.path, "SELECT title, timesplayed, duration FROM library") == [("B", 7, 300.0)]


def test_key_written(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3")
    mixxx.close()
    library = replaced(read(mixxx.path), "/music/a.mp3", key=Key(tonic=9, mode=Mode.MINOR))

    written(plan(library, mixxx.path))

    assert rows(mixxx.path, "SELECT key_id, key, keys_version FROM library") == [
        (22, "1m", "KeyMap-1.0")
    ]
    assert by_path(read(mixxx.path), "/music/a.mp3").key == Key(tonic=9, mode=Mode.MINOR)


def test_fields_round_trip(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3")
    mixxx.close()
    values = {
        "artist": "Artist",
        "album": "Album",
        "genre": "Techno",
        "comment": "Note",
        "year": 2024,
        "track_number": 3,
        "rating": 4,
        "color": "#FF8000",
        "bpm": 127.5,
    }
    library = replaced(read(mixxx.path), "/music/a.mp3", **values)

    written(plan(library, mixxx.path))

    track = by_path(read(mixxx.path), "/music/a.mp3")
    assert {name: getattr(track, name) for name in values} == values


# Cues and grids


def test_hot_cue_written(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3")
    mixxx.close()
    cue = Cue(kind=CueKind.HOT, start_us=30_000_000, slot=0, color="#FF8000")
    library = replaced(read(mixxx.path), "/music/a.mp3", cues=(cue,))

    written(plan(library, mixxx.path))

    assert rows(mixxx.path, "SELECT type, position, hotcue, color FROM cues") == [
        (HOT_CUE, 2_646_000, 0, 0xFF8000)
    ]
    assert by_path(read(mixxx.path), "/music/a.mp3").cues == (cue,)


def test_extra_memory_cues(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3")
    mixxx.close()
    cues = tuple(Cue(kind=CueKind.MEMORY, start_us=s * 1_000_000) for s in (1, 2, 3))
    library = replaced(read(mixxx.path), "/music/a.mp3", cues=cues)

    write_plan = plan(library, mixxx.path)
    written(write_plan)

    assert rows(mixxx.path, "SELECT type, position FROM cues") == [(2, 88200)]
    assert rows(mixxx.path, "SELECT cuepoint FROM library") == [(88200,)]
    (loss,) = [loss for loss in write_plan.losses if loss.kind == "memory-cues"]
    assert loss.count == 2


def test_intro_kept_and_loops_written(mixxx: MixxxDatabase) -> None:
    a = mixxx.add_track("/music/a.mp3")
    mixxx.add_cue(a, INTRO, 1000, length=5000)
    mixxx.add_cue(a, HOT_CUE, 5000, hotcue=1)
    mixxx.close()
    loop = Cue(kind=CueKind.LOOP, start_us=1_000_000, end_us=5_000_000, slot=2, color="#00FF00")
    library = replaced(read(mixxx.path), "/music/a.mp3", cues=(loop,))

    written(plan(library, mixxx.path))

    assert rows(mixxx.path, "SELECT type, position, length, hotcue FROM cues ORDER BY id") == [
        (INTRO, 1000, 5000, -1),
        (4, 88200, 352800, 2),
    ]
    track = by_path(read(mixxx.path), "/music/a.mp3")
    assert track.cues == (loop,)
    assert track.unmapped["mixxx"]["intro"] is not None  # type: ignore[index]


def test_pads_beyond_36(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3")
    mixxx.close()
    cue = Cue(kind=CueKind.HOT, start_us=1_000_000, slot=40)
    write_plan = plan(replaced(read(mixxx.path), "/music/a.mp3", cues=(cue,)), mixxx.path)

    assert [loss.kind for loss in write_plan.losses] == ["pads-beyond-36"]


def test_unknown_sample_rate_keeps_cues(mixxx: MixxxDatabase) -> None:
    a = mixxx.add_track("/music/a.mp3", samplerate=None)
    mixxx.add_cue(a, HOT_CUE, 5000, hotcue=1)
    mixxx.close()
    cue = Cue(kind=CueKind.HOT, start_us=1_000_000, slot=0)
    library = replaced(read(mixxx.path), "/music/a.mp3", cues=(cue,))

    write_plan = plan(library, mixxx.path)
    written(write_plan)

    assert rows(mixxx.path, "SELECT position, hotcue FROM cues") == [(5000, 1)]
    assert any("sample rate is unknown" in w for w in write_plan.warnings)


def test_constant_grid_round_trip(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3", duration=300.0)
    mixxx.close()
    grid = BeatGrid(markers=(BeatMarker(position_us=500_000, bpm=128.0),))
    library = replaced(read(mixxx.path), "/music/a.mp3", beatgrid=grid)

    written(plan(library, mixxx.path))

    assert by_path(read(mixxx.path), "/music/a.mp3").beatgrid == grid
    assert rows(mixxx.path, "SELECT beats_version FROM library") == [("BeatGrid-2.0",)]


def test_beat_map_round_trip(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/a.mp3", duration=30.0)
    mixxx.close()
    grid = BeatGrid(
        markers=(BeatMarker(position_us=0, bpm=120.0), BeatMarker(position_us=8_000_000, bpm=125.0))
    )
    library = replaced(read(mixxx.path), "/music/a.mp3", beatgrid=grid)

    written(plan(library, mixxx.path))

    assert by_path(read(mixxx.path), "/music/a.mp3").beatgrid == grid


# New and removed tracks


def test_scanned_track_added(mixxx: MixxxDatabase, tmp_path: Path) -> None:
    mixxx.close()
    music = tmp_path / "music" / "a.mp3"
    music.parent.mkdir()
    music.write_bytes(b"x" * 100)
    track = Track(
        path_origin=str(music), title="A", bpm=128.0, duration_us=300_000_000, sample_rate=44100
    )

    written(plan(Library.build([track]), mixxx.path))

    added = by_path(read(mixxx.path), track.path)
    assert (added.title, added.bpm, added.duration_us) == ("A", 128.0, 300_000_000)
    query = (
        "SELECT header_parsed, filesize FROM library"
        " JOIN track_locations ON library.location = track_locations.id"
    )
    assert rows(mixxx.path, query) == [(1, 100)]


def test_removed_track_not_revived(mixxx: MixxxDatabase) -> None:
    mixxx.add_track("/music/gone.mp3", removed=True)
    mixxx.close()
    gone = Track(path_origin="/music/gone.mp3", title="Gone")
    kept = Track(path_origin="/music/kept.mp3", title="Kept")
    library = Library.build([gone, kept], [Playlist(name="P", entries=(gone.id, kept.id))])

    write_plan = plan(library, mixxx.path)
    written(write_plan)

    assert rows(mixxx.path, "SELECT mixxx_deleted FROM library ORDER BY id") == [(1,), (0,)]
    (playlist,) = [n for n in read(mixxx.path).walk() if n[2].name == "P"]
    assert isinstance(playlist[2], Playlist) and len(playlist[2].entries) == 1
    assert "removed-in-mixxx" in [loss.kind for loss in write_plan.losses]


# Playlists and crates


def test_own_playlist_written(mixxx: MixxxDatabase) -> None:
    a = Track(path_origin="/music/a.mp3")
    b = Track(path_origin="/music/b.mp3")
    peak = Playlist(name="Peak", entries=(b.id, a.id, b.id))
    library = Library.build([a, b], [Folder(name="Techno", children=(peak,))])
    mixxx.close()

    write_plan = plan(library, mixxx.path)
    written(write_plan)

    assert rows(mixxx.path, "SELECT name FROM Playlists WHERE hidden = 0") == [("Techno / Peak",)]
    assert rows(
        mixxx.path,
        "SELECT track_locations.location FROM PlaylistTracks JOIN library ON library.id = track_id"
        " JOIN track_locations ON track_locations.id = library.location ORDER BY position",
    ) == [("/music/b.mp3",), ("/music/a.mp3",), ("/music/b.mp3",)]
    assert write_plan.view is not None
    (playlists, _crates) = write_plan.view.playlists
    assert isinstance(playlists, Folder) and [c.id for c in playlists.children] == [peak.id]
    assert [loss.kind for loss in write_plan.losses] == []


def test_imported_crate_written_back(mixxx: MixxxDatabase) -> None:
    a, b = mixxx.add_track("/music/a.mp3"), mixxx.add_track("/music/b.mp3")
    crate = mixxx.add_crate("Techno", [a])
    mixxx.close()
    read_library = read(mixxx.path)
    root = Folder(name="Mixxx", children=read_library.playlists)
    library = dataclasses.replace(read_library, playlists=(root,))
    (crates,) = [n for n in root.children if n.name == "Crates"]
    assert isinstance(crates, Folder)
    (techno,) = crates.children
    assert isinstance(techno, Playlist)
    b_id = by_path(library, "/music/b.mp3").id
    new_crates = dataclasses.replace(
        crates, children=(dataclasses.replace(techno, entries=(*techno.entries, b_id)),)
    )
    root = dataclasses.replace(
        root, children=tuple(new_crates if n.name == "Crates" else n for n in root.children)
    )
    library = dataclasses.replace(library, playlists=(root,))

    written(plan(library, mixxx.path, source_root=root.id))

    assert rows(mixxx.path, "SELECT id, name FROM crates") == [(crate, "Techno")]
    assert sorted(rows(mixxx.path, "SELECT track_id FROM crate_tracks")) == [(a,), (b,)]
    assert rows(mixxx.path, "SELECT count(*) FROM Playlists WHERE hidden = 0") == [(0,)]


def test_locked_playlist(mixxx: MixxxDatabase) -> None:
    a = mixxx.add_track("/music/a.mp3")
    peak = mixxx.add_playlist("Peak", [])
    mixxx.db.execute("UPDATE Playlists SET locked = 1 WHERE id = ?", (peak,))
    mixxx.db.commit()
    mixxx.close()
    track = by_path(read(mixxx.path), "/music/a.mp3")
    library = Library.build([track], [Playlist(name="Peak", entries=(track.id,))])

    write_plan = plan(library, mixxx.path)
    written(write_plan)

    assert rows(mixxx.path, "SELECT count(*) FROM PlaylistTracks WHERE playlist_id = ?", peak) == [
        (0,)
    ]
    assert any("'Peak' is locked" in w for w in write_plan.warnings)
    assert a


def test_extra_and_hidden_lists_untouched(mixxx: MixxxDatabase) -> None:
    a = mixxx.add_track("/music/a.mp3")
    mixxx.add_playlist("Extra", [a])
    mixxx.add_playlist("2026-10-27", [a], hidden=2)
    mixxx.close()
    track = by_path(read(mixxx.path), "/music/a.mp3")
    library = Library.build([track], [Playlist(name="New", entries=(track.id,))])
    before = rows(mixxx.path, "SELECT * FROM PlaylistTracks ORDER BY id")

    written(plan(library, mixxx.path))

    after = rows(mixxx.path, "SELECT * FROM PlaylistTracks ORDER BY id")
    assert after[: len(before)] == before
    assert len(after) == len(before) + 1


def test_smartlists_lost(mixxx: MixxxDatabase) -> None:
    mixxx.close()
    write_plan = plan(Library.build([], [Smartlist(name="Smart")]), mixxx.path)

    assert [loss.kind for loss in write_plan.losses] == ["smartlists"]


def test_tags_lost(mixxx: MixxxDatabase) -> None:
    mixxx.close()
    track = Track(path_origin="/music/a.mp3", tags=("dark",))

    assert "tags" in [loss.kind for loss in plan(Library.build([track]), mixxx.path).losses]


def test_selected_playlist_writes_only_its_tracks(mixxx: MixxxDatabase) -> None:
    mixxx.close()
    a, b = Track(path_origin="/music/a.mp3"), Track(path_origin="/music/b.mp3")
    peak, warm = Playlist(name="Peak", entries=(a.id,)), Playlist(name="Warm", entries=(b.id,))
    library = Library.build([a, b], [peak, warm])

    written(plan(library, mixxx.path, selection=frozenset({peak.id})))

    assert rows(mixxx.path, "SELECT location FROM track_locations") == [("/music/a.mp3",)]
    assert rows(mixxx.path, "SELECT name FROM Playlists WHERE hidden = 0") == [("Peak",)]
