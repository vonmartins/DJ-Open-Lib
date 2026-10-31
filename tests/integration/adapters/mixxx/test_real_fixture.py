"""A real Mixxx 2.5.6 database, sanitized (see tests/fixtures/mixxx/README.md)."""

import dataclasses
from pathlib import Path

from support.adapter_contract import assert_read_only
from tunedex.adapters.contract import WriteOptions
from tunedex.adapters.mixxx import MixxxAdapter
from tunedex.model.cue import CueKind
from tunedex.model.key import Key, Mode
from tunedex.model.playlist import Folder, Playlist

FIXTURE = Path(__file__).parents[3] / "fixtures" / "mixxx" / "real-2.5.6.sqlite"
MS = 1_000


def near(actual: int | None, expected: int) -> bool:
    return actual is not None and abs(actual - expected) <= MS


def test_real_database() -> None:
    result = assert_read_only(MixxxAdapter(), FIXTURE)
    library = result.library
    track = next(t for t in library.tracks.values() if t.path == "/music/01.mp3")

    assert len(library.tracks) == 15
    assert (track.bpm, track.key, track.key_original) == (
        140.0,
        Key(tonic=4, mode=Mode.MINOR),
        "2m",
    )
    hot = {c.slot: c for c in track.cues if c.kind is CueKind.HOT}
    assert near(hot[0].start_us, 30_009_735)  # placed by hand at 0:30.000
    assert near(hot[1].start_us, 154_524_172)
    loops = [c for c in track.cues if c.kind is CueKind.LOOP]
    assert len(loops) == 2 and {c.slot for c in loops} == {None, 2}
    assert all(near(c.start_us, 182_381_315) and near(c.end_us, 184_095_601) for c in loops)
    (main,) = [c for c in track.cues if c.kind is CueKind.MEMORY]
    assert near(main.start_us, 21_497)
    assert hot[0].color == "#FF8000"

    assert track.beatgrid is not None
    (marker,) = track.beatgrid.markers
    assert marker.bpm == 140.0 and near(marker.position_us, 238_458)
    # The quantized hot cue falls exactly on a beat of the grid.
    beats = (hot[1].start_us - marker.position_us) / (60 / marker.bpm * 1_000_000)
    assert abs(beats - round(beats)) < 0.001

    assert track.unmapped["mixxx"]["intro"] == {"start_us": 21_497}  # type: ignore[index]
    assert near(track.unmapped["mixxx"]["outro"]["end_us"], 322_458_424)  # type: ignore[index, arg-type]

    playlists, crates = library.playlists
    assert isinstance(playlists, Folder) and isinstance(crates, Folder)
    assert [(p.name, len(p.entries)) for p in playlists.children if isinstance(p, Playlist)] == [
        ("Warmup", 6),
        ("Peak", 5),
    ]
    assert [c.name for c in crates.children] == ["Techno"]
    assert "not imported: 1 Auto DJ queue, 1 history playlists" in result.warnings


def test_keys_match_the_key_text() -> None:
    """Mixxx was set to Open Key notation, so its key text must equal our rendering."""
    library = MixxxAdapter().read(FIXTURE).library

    keyed = [t for t in library.tracks.values() if t.key is not None]
    assert len(keyed) == 13
    assert all(t.key is not None and t.key.open_key() == t.key_original for t in keyed)


def test_real_database_rewritten_unchanged(tmp_path: Path) -> None:
    """Writing back exactly what was read changes nothing in a real database."""
    copy = tmp_path / "mixxxdb.sqlite"
    copy.write_bytes(FIXTURE.read_bytes())
    adapter = MixxxAdapter(running=lambda: False)
    library = adapter.read(copy).library
    root = Folder(name="Mixxx", children=library.playlists)
    library = dataclasses.replace(library, playlists=(root,))

    write_plan = adapter.plan_write(library, copy, WriteOptions(source_root=root.id))

    assert write_plan.changes == ()
    assert write_plan.losses == ()
