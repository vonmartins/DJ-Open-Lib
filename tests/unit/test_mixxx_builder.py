import sqlite3
from pathlib import Path

from support.mixxx import HOT_CUE, MixxxDatabase, beat_grid


def test_builder_makes_a_schema_39_database(tmp_path: Path) -> None:
    database = MixxxDatabase(tmp_path / "mixxxdb.sqlite")
    track = database.add_track("/music/a.mp3", artist="A", title="T", bpm=128.0)
    database.add_cue(track, HOT_CUE, 2_646_000, hotcue=0)
    database.set_beats(track, beat_grid(128.0, 22050))
    database.add_playlist("Peak", [track, track])
    database.add_crate("Techno", [track])
    database.close()

    db = sqlite3.connect(tmp_path / "mixxxdb.sqlite")
    assert db.execute(
        "SELECT value FROM settings WHERE name = 'mixxx.schema.version'"
    ).fetchone() == ("39",)
    assert db.execute("SELECT count(*) FROM PlaylistTracks").fetchone() == (2,)
    assert db.execute(
        "SELECT l.location FROM library JOIN track_locations l ON library.location = l.id"
    ).fetchone() == ("/music/a.mp3",)
    db.close()
