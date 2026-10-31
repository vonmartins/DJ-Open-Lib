"""Reading beets libraries (specs/source-beets), on both beets schemas."""

import datetime
from pathlib import Path

import pytest

from support.adapter_contract import assert_read_only
from support.beets import BeetsDatabase
from support.mixxx import MixxxDatabase
from tunedex.adapters.errors import AdapterError, AdapterReadError
from tunedex.model.key import Key, Mode
from tunedex.model.library import Library
from tunedex.model.paths import normalize_path
from tunedex.model.track import Track
from tunedex.sources.beets import BeetsSource

SOURCE = BeetsSource()
ADDED = datetime.datetime(2026, 2, 20, 12, 0, tzinfo=datetime.UTC).timestamp()


@pytest.fixture(params=["legacy", "2.14"])
def beets(request: pytest.FixtureRequest, tmp_path: Path) -> BeetsDatabase:
    return BeetsDatabase(tmp_path / "beets" / "library.db", schema=request.param)


def read(database: BeetsDatabase, **options: object) -> tuple[Library, tuple[str, ...]]:
    result = assert_read_only(BeetsSource(**options), database.path)  # type: ignore[arg-type]
    return result.library, result.warnings


def only(library: Library) -> Track:
    (track,) = library.tracks.values()
    return track


def genres(database: BeetsDatabase, *values: str) -> dict[str, object]:
    if database.schema == "2.14":
        return {"genres": list(values)}
    return {"genre": ", ".join(values)}


# Detection


def test_detects_file_and_directory(beets: BeetsDatabase) -> None:
    assert SOURCE.detect(beets.path).matches
    assert SOURCE.detect(beets.path.parent).matches


def test_mixxx_database_does_not_match(tmp_path: Path) -> None:
    mixxx = MixxxDatabase(tmp_path / "mixxxdb.sqlite")
    mixxx.close()

    detection = SOURCE.detect(mixxx.path)

    assert not detection.matches and "items" in detection.reason


def test_files_unchanged(beets: BeetsDatabase) -> None:
    beets.add_item("/music/a.mp3", title="A")

    read(beets)  # assert_read_only compares bytes and modification times


# Fields


def test_text_fields_read(beets: BeetsDatabase) -> None:
    beets.add_item(
        "/music/a.mp3",
        title="Glue",
        artist="Bicep",
        album="Isles",
        albumartist="Bicep",
        label="Ninja Tune",
        comments="Note",
        grouping="Peak",
        **genres(beets, "Techno"),
    )

    track = only(read(beets)[0])

    assert (track.title, track.artist, track.album, track.album_artist) == (
        "Glue",
        "Bicep",
        "Isles",
        "Bicep",
    )
    assert (track.label, track.comment, track.grouping, track.genre) == (
        "Ninja Tune",
        "Note",
        "Peak",
        "Techno",
    )


def test_list_fields(tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "library.db", schema="2.14")
    beets.add_item(
        "/music/a.mp3",
        genres=["Techno", "Minimal"],
        remixers=["A", "B"],
        composers=["C"],
        lyricists=[],
    )

    track = only(read(beets)[0])

    assert (track.genre, track.remixer, track.composer, track.lyricist) == (
        "Techno, Minimal",
        "A, B",
        "C",
        None,
    )


def test_legacy_single_fields(tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "library.db", schema="legacy")
    beets.add_item("/music/a.mp3", composer="C", lyricist="L")

    track = only(read(beets)[0])

    assert (track.composer, track.lyricist, track.remixer) == ("C", "L", None)


def test_track_read(beets: BeetsDatabase) -> None:
    beets.add_item(
        "/music/a.mp3",
        bpm=128,
        length=300.5,
        bitrate=320000,
        samplerate=44100,
        added=ADDED,
        year=2021,
        month=3,
        day=5,
        track=4,
        disc=1,
        format="MP3",
    )

    track = only(read(beets)[0])

    assert (track.bpm, track.duration_us, track.bitrate, track.sample_rate) == (
        128.0,
        300_500_000,
        320,
        44100,
    )
    assert track.date_added == datetime.date(2026, 2, 20)
    assert (track.year, track.release_date) == (2021, datetime.date(2021, 3, 5))
    assert (track.track_number, track.disc_number, track.file_format) == (4, 1, "mp3")


def test_zero_bpm(beets: BeetsDatabase) -> None:
    beets.add_item("/music/a.flac", bpm=0, year=0, month=0, day=0, track=0)

    track = only(read(beets)[0])

    assert (track.bpm, track.year, track.release_date, track.track_number) == (
        None,
        None,
        None,
        None,
    )
    assert track.file_format == "flac"


def test_both_key_notations(beets: BeetsDatabase) -> None:
    beets.add_item("/music/a.mp3", initial_key="12d")
    beets.add_item("/music/b.mp3", initial_key="Gm")
    beets.add_item("/music/c.mp3", initial_key="nonsense")

    tracks = {t.path: t for t in read(beets)[0].tracks.values()}

    assert tracks["/music/a.mp3"].key == Key(tonic=5, mode=Mode.MAJOR)
    assert tracks["/music/b.mp3"].key == Key(tonic=7, mode=Mode.MINOR)
    assert (tracks["/music/c.mp3"].key, tracks["/music/c.mp3"].key_original) == (
        None,
        "nonsense",
    )
    assert tracks["/music/a.mp3"].key_original == "12d"


def test_musicbrainz_id_kept(beets: BeetsDatabase) -> None:
    item = beets.add_item(
        "/music/a.mp3",
        mb_trackid="mbid",
        catalognum="CAT 001",
        lyrics="la la",
        acoustid_fingerprint="AQAA",
    )
    beets.set_attributes(item, {"data_source": "MusicBrainz"})

    data = only(read(beets)[0]).unmapped["beets"]

    assert data == {
        "id": item,
        "mb_trackid": "mbid",
        "catalognum": "CAT 001",
        "attributes": {"data_source": "MusicBrainz"},
    }


def test_album_not_a_playlist(beets: BeetsDatabase) -> None:
    items = [beets.add_item(f"/music/{n:02d}.mp3", title=str(n)) for n in range(10)]
    beets.add_album("Isles", items)

    library, _warnings = read(beets)

    assert len(library.tracks) == 10 and library.playlists == ()
    assert {t.album for t in library.tracks.values()} == {"Isles"}


# Paths


def test_undecodable_path_kept(beets: BeetsDatabase) -> None:
    beets.add_item(b"/music/caf\xe9.mp3", title="A")

    track = only(read(beets)[0])

    assert track.path_origin.startswith("/music/caf")


def test_relative_path(tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "library.db", schema="2.14")
    beets.add_item("Techno/a.mp3", title="A")
    beets.add_item("/elsewhere/b.mp3", title="B")

    music = tmp_path / "music"  # absolute on every platform

    library, _warnings = read(beets, music_dir=music)

    paths = {t.title: t.path for t in library.tracks.values()}
    assert paths == {
        "A": normalize_path(str(music / "Techno" / "a.mp3")),
        "B": "/elsewhere/b.mp3",
    }


def test_music_directory_unknown(tmp_path: Path) -> None:
    beets = BeetsDatabase(tmp_path / "library.db", schema="2.14")
    beets.add_item("Techno/a.mp3", title="A")

    with pytest.raises(AdapterReadError, match="--music-dir"):
        SOURCE.read(beets.path)


def test_item_without_a_path_skipped(beets: BeetsDatabase) -> None:
    beets.add_item(b"", title="Empty")
    beets.add_item("/music/a.mp3", title="A")

    library, warnings = read(beets)

    assert [t.title for t in library.tracks.values()] == ["A"]
    assert warnings == ("1 items without a path were skipped",)


# Writing


def test_write_refused(beets: BeetsDatabase) -> None:
    with pytest.raises(AdapterError, match="only read"):
        SOURCE.plan_write(Library(), beets.path)


def test_keys_from_a_database(beets: BeetsDatabase) -> None:
    item = beets.add_item("/music/a.mp3", title="A")

    result = SOURCE.read(beets.path)

    (track,) = result.library.tracks.values()
    assert result.keys == {track.id: str(item)}
