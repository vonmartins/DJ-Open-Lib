import datetime
from pathlib import Path

import pytest

from djlib.adapters.errors import AdapterError, AdapterReadError
from djlib.adapters.mixxx import MixxxAdapter
from djlib.adapters.registry import get_adapter
from djlib.model.beatgrid import BeatGrid, BeatMarker
from djlib.model.cue import Cue, CueKind
from djlib.model.key import Key, Mode
from djlib.model.library import Library
from djlib.model.playlist import Folder, Playlist
from djlib.model.track import Track
from djlib.store import Store
from support.adapter_contract import assert_read_only, tree_state
from support.mixxx import (
    BEAT,
    HOT_CUE,
    INTRO,
    JUMP,
    LOOP,
    MAIN_CUE,
    OUTRO,
    MixxxDatabase,
    beat_grid,
    beat_map,
)

MIXXX = MixxxAdapter()
RATE = 44100


def samples(seconds: float) -> int:
    """Mixxx's engine sample position: frames times two channels."""
    return round(seconds * RATE) * 2


@pytest.fixture
def database(tmp_path: Path) -> MixxxDatabase:
    return MixxxDatabase(tmp_path / "profile" / "mixxxdb.sqlite")


def read(database: MixxxDatabase) -> tuple[Library, tuple[str, ...]]:
    database.close()
    result = assert_read_only(MIXXX, database.path.parent)
    return result.library, result.warnings


def only_track(library: Library) -> Track:
    (track,) = library.tracks.values()
    return track


def folder(library: Library, name: str) -> Folder:
    (node,) = [n for n in library.playlists if n.name == name]
    assert isinstance(node, Folder)
    return node


# Detection and opening


def test_detects_file_and_directory(database: MixxxDatabase) -> None:
    database.close()

    assert MIXXX.detect(database.path).matches
    assert MIXXX.detect(database.path.parent).matches
    assert "39" in MIXXX.detect(database.path).reason


def test_other_sqlite_file_does_not_match(tmp_path: Path) -> None:
    with Store.open(tmp_path / "library.db"):
        pass

    detection = MIXXX.detect(tmp_path / "library.db")

    assert not detection.matches
    assert "no Mixxx schema version" in detection.reason
    assert not MIXXX.detect(tmp_path / "nope.sqlite").matches


def test_files_unchanged(database: MixxxDatabase) -> None:
    database.add_track("/music/a.mp3", title="A")
    database.close()
    before = tree_state(database.path.parent)

    MIXXX.read(database.path)
    MIXXX.read(database.path.parent)

    assert tree_state(database.path.parent) == before


def test_reads_while_another_connection_is_open(database: MixxxDatabase) -> None:
    database.add_track("/music/a.mp3", title="A")
    database.db.execute("BEGIN")
    database.db.execute("UPDATE library SET title = 'uncommitted'")

    library = MIXXX.read(database.path).library
    database.db.rollback()
    database.close()

    assert only_track(library).title == "A"


def test_old_schema(tmp_path: Path) -> None:
    database = MixxxDatabase(tmp_path / "mixxxdb.sqlite", schema_version=30)
    database.close()

    with pytest.raises(AdapterReadError, match=r"version 30 is too old; version 39"):
        MIXXX.read(database.path)


def test_newer_schema_warns(tmp_path: Path) -> None:
    database = MixxxDatabase(tmp_path / "mixxxdb.sqlite", schema_version=40)

    _, warnings = read(database)

    assert any("newer than the tested version 39" in w for w in warnings)


# Tracks


def test_track_read(database: MixxxDatabase) -> None:
    database.add_track(
        "/music/glue.mp3",
        artist="Bicep",
        title="Glue",
        album="",
        year="2017-01-01",
        tracknumber="3",
        bpm=127.0,
        key_id=22,
        key="Am",
        rating=4,
        color=0xFF8800,
        duration=269.5,
        bitrate=320,
        filetype="mp3",
        timesplayed=7,
        last_played_at="2026-10-01 21:30:00",
        datetime_added="2026-09-01 10:00:00",
        bpm_lock=1,
        replaygain=0.5,
    )

    library, _ = read(database)

    track = only_track(library)
    assert (track.path, track.artist, track.title, track.album) == (
        "/music/glue.mp3",
        "Bicep",
        "Glue",
        None,
    )
    assert (track.year, track.track_number, track.bpm) == (2017, 3, 127.0)
    assert (track.key, track.key_original) == (Key(tonic=9, mode=Mode.MINOR), "Am")
    assert (track.rating, track.color, track.play_count) == (4, "#FF8800", 7)
    assert (track.duration_us, track.bitrate, track.sample_rate, track.file_format) == (
        269_500_000,
        320,
        RATE,
        "mp3",
    )
    assert track.last_played == datetime.datetime(2026, 10, 1, 21, 30, tzinfo=datetime.UTC)
    assert track.date_added == datetime.date(2026, 9, 1)
    assert track.unmapped["mixxx"] == {
        "id": 1,
        "replaygain": 0.5,
        "replaygain_peak": -1.0,
        "bpm_lock": True,
    }


def test_unanalysed_track(database: MixxxDatabase) -> None:
    database.add_track("/music/a.mp3", bpm=0.0, key_id=0, key="", title="", artist="  ")

    track = only_track(read(database)[0])

    assert (track.bpm, track.key, track.key_original, track.title, track.artist) == (None,) * 5


@pytest.mark.parametrize(
    ("key_id", "expected"), [(1, "C"), (12, "B"), (13, "Cm"), (24, "Bm"), (2, "Db")]
)
def test_key_ids(database: MixxxDatabase, key_id: int, expected: str) -> None:
    database.add_track("/music/a.mp3", key_id=key_id)

    key = only_track(read(database)[0]).key

    assert key is not None and key.musical() == expected


def test_removed_track_skipped(database: MixxxDatabase) -> None:
    database.add_track("/music/a.mp3")
    database.add_track("/music/b.mp3", missing=True)
    database.add_track("/music/c.mp3", removed=True)

    library, warnings = read(database)

    assert sorted(t.path for t in library.tracks.values()) == ["/music/a.mp3", "/music/b.mp3"]
    assert "1 tracks have files that Mixxx reports as missing" in warnings


def test_invalid_value_dropped_with_warning(database: MixxxDatabase) -> None:
    database.add_track("/music/a.mp3", rating=9, title="A")

    library, warnings = read(database)

    assert (only_track(library).rating, only_track(library).title) == (None, "A")
    assert any("ignored invalid rating" in w for w in warnings)


# Cues and grids


def test_hot_cue_time(database: MixxxDatabase) -> None:
    track = database.add_track("/music/a.mp3")
    database.add_cue(track, HOT_CUE, 2_646_000, hotcue=0, label="Drop", color=0x00FF00)

    (cue,) = only_track(read(database)[0]).cues

    assert cue == Cue(kind=CueKind.HOT, start_us=30_000_000, slot=0, name="Drop", color="#00FF00")


def test_cue_kinds(database: MixxxDatabase) -> None:
    track = database.add_track("/music/a.mp3")
    database.add_cue(track, MAIN_CUE, samples(1))
    database.add_cue(track, LOOP, samples(10), length=samples(4), hotcue=2, label="Groove")
    database.add_cue(track, LOOP, samples(20), length=samples(2))
    database.add_cue(track, INTRO, samples(0.5), length=samples(15))
    database.add_cue(track, OUTRO, -1, length=samples(200) + 1)  # start unset, as Mixxx does
    database.add_cue(track, JUMP, samples(5))
    database.add_cue(track, BEAT, samples(6))
    database.add_cue(track, HOT_CUE, -1, hotcue=3)

    library, warnings = read(database)

    loaded = only_track(library)
    assert sorted(loaded.cues, key=lambda c: c.start_us) == [
        Cue(kind=CueKind.MEMORY, start_us=1_000_000, name="Main cue"),
        Cue(
            kind=CueKind.LOOP,
            start_us=10_000_000,
            end_us=14_000_000,
            slot=2,
            name="Groove",
            color="#FF0000",
        ),
        Cue(kind=CueKind.LOOP, start_us=20_000_000, end_us=22_000_000, color="#FF0000"),
    ]
    assert loaded.unmapped["mixxx"]["intro"] == {"start_us": 500_000, "end_us": 15_500_000}  # type: ignore[index]
    assert loaded.unmapped["mixxx"]["outro"] == {"end_us": 200_000_000}  # type: ignore[index]
    assert "2 cues of kinds djlib does not keep (beat, jump, silence) were skipped" in warnings
    assert "1 cues without a position were skipped" in warnings


def test_cues_without_sample_rate(database: MixxxDatabase) -> None:
    track = database.add_track("/music/a.mp3", samplerate=None)
    database.add_cue(track, HOT_CUE, samples(1), hotcue=0)

    library, warnings = read(database)

    assert only_track(library).cues == ()
    assert any("sample rate is unknown" in w for w in warnings)


def test_constant_grid(database: MixxxDatabase) -> None:
    track = database.add_track("/music/a.mp3")
    database.set_beats(track, beat_grid(128.0, RATE // 2))

    grid = only_track(read(database)[0]).beatgrid

    assert grid == BeatGrid(markers=(BeatMarker(position_us=500_000, bpm=128.0, beat=1),))


def test_grid_starting_before_zero(database: MixxxDatabase) -> None:
    track = database.add_track("/music/a.mp3")
    database.set_beats(track, beat_grid(120.0, -RATE // 4))  # beats every 0.5 s from -0.25 s

    grid = only_track(read(database)[0]).beatgrid

    assert grid == BeatGrid(markers=(BeatMarker(position_us=250_000, bpm=120.0, beat=2),))


def test_beat_map_with_a_tempo_change(database: MixxxDatabase) -> None:
    track = database.add_track("/music/a.mp3")
    at_120 = [i * RATE // 2 for i in range(9)]  # 0 .. 4 s
    at_60 = [at_120[-1] + i * RATE for i in range(1, 5)]
    database.set_beats(track, beat_map([*at_120, *at_60], disabled=[at_120[3] + 1]), "BeatMap-1.0")

    grid = only_track(read(database)[0]).beatgrid

    assert grid == BeatGrid(
        markers=(
            BeatMarker(position_us=0, bpm=120.0, beat=1),
            BeatMarker(position_us=4_000_000, bpm=60.0, beat=1),
        )
    )


def test_unknown_grid_kept_raw(database: MixxxDatabase) -> None:
    track = database.add_track("/music/a.mp3")
    database.set_beats(track, b"\x01\x02", "BeatGrid-1.0")

    library, warnings = read(database)

    loaded = only_track(library)
    assert loaded.beatgrid is None
    assert loaded.unmapped["mixxx"]["beats"]["version"] == "BeatGrid-1.0"  # type: ignore[index]
    assert any("'BeatGrid-1.0' not read (unknown format)" in w for w in warnings)


def test_damaged_grid(database: MixxxDatabase) -> None:
    track = database.add_track("/music/a.mp3")
    database.set_beats(track, b"\x0a\xff")

    library, warnings = read(database)

    assert only_track(library).beatgrid is None
    assert any("beat grid 'BeatGrid-2.0' not read" in w for w in warnings)


# Playlists and crates


def test_playlists_and_crates(database: MixxxDatabase) -> None:
    a = database.add_track("/music/a.mp3")
    b = database.add_track("/music/b.mp3")
    gone = database.add_track("/music/gone.mp3", removed=True)
    database.add_playlist("Warmup", [b, a, b])
    database.add_playlist("Peak", [a, gone])
    database.add_crate("Techno", [b, a])
    database.add_playlist("2026-10-01", [a], hidden=2)
    database.add_playlist("2026-10-02", [b], hidden=2)

    library, warnings = read(database)

    ids = {t.path: t.id for t in library.tracks.values()}
    playlists, crates = folder(library, "Playlists"), folder(library, "Crates")
    assert [n.name for n in library.playlists] == ["Playlists", "Crates"]
    assert [(p.name, p.entries) for p in playlists.children if isinstance(p, Playlist)] == [
        ("Warmup", (ids["/music/b.mp3"], ids["/music/a.mp3"], ids["/music/b.mp3"])),
        ("Peak", (ids["/music/a.mp3"],)),
    ]
    (techno,) = crates.children
    assert isinstance(techno, Playlist)
    assert techno.entries == (ids["/music/a.mp3"], ids["/music/b.mp3"])
    assert "not imported: 1 Auto DJ queue, 2 history playlists" in warnings
    assert "1 playlist entries point at tracks that were not read" in warnings


# Contract


def test_capabilities_and_registry() -> None:
    capabilities = MIXXX.capabilities

    assert capabilities.cue_kinds == {CueKind.HOT, CueKind.MEMORY, CueKind.LOOP}
    assert capabilities.beatgrid and capabilities.collection
    assert not (capabilities.folders or capabilities.tags or capabilities.smartlists)
    assert isinstance(get_adapter("mixxx"), MixxxAdapter)


def test_write_refused(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="writing to Mixxx is not supported yet"):
        MIXXX.plan_write(Library(), tmp_path / "mixxxdb.sqlite")
