from hypothesis import given
from hypothesis import strategies as st

from djlib.adapters.mixxx.beats import (
    BEAT_GRID,
    BEAT_MAP,
    decode_grid,
    decode_map,
    encode_grid,
    encode_map,
    grid_from_mixxx,
    grid_to_mixxx,
)
from djlib.adapters.mixxx.keys import encode_key_map, key_from_id, key_to_id
from djlib.model.beatgrid import BeatGrid, BeatMarker
from support.mixxx import beat_grid, beat_map

RATE = 44100


def test_grid_round_trip() -> None:
    grid = BeatGrid(markers=(BeatMarker(position_us=500_000, bpm=128.0),))

    version, blob = grid_to_mixxx(grid, RATE, None) or ("", b"")

    assert version == BEAT_GRID
    assert grid_from_mixxx(version, blob, RATE) == grid


@given(
    bpm=st.floats(min_value=40, max_value=300, allow_nan=False),
    frame=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_grid_message_round_trip(bpm: float, frame: int) -> None:
    assert decode_grid(encode_grid(bpm, frame)) == (bpm, frame)


def test_messages_readable_by_the_independent_encoding() -> None:
    # The test encoder writes no source fields; both decode the same way.
    assert decode_grid(encode_grid(128.0, 22050)) == decode_grid(beat_grid(128.0, 22050))
    assert decode_map(encode_map([0, 100, 200])) == decode_map(beat_map([0, 100, 200]))


def test_map_round_trip() -> None:
    grid = BeatGrid(
        markers=(
            BeatMarker(position_us=0, bpm=120.0),
            BeatMarker(position_us=8_000_000, bpm=125.0, beat=1),
        )
    )

    version, blob = grid_to_mixxx(grid, RATE, 20 * RATE) or ("", b"")

    assert version == BEAT_MAP
    assert grid_from_mixxx(version, blob, RATE) == grid


def test_map_needs_a_duration() -> None:
    grid = BeatGrid(
        markers=(BeatMarker(position_us=0, bpm=120.0), BeatMarker(position_us=8_000_000, bpm=125.0))
    )
    assert grid_to_mixxx(grid, RATE, None) is None


def test_key_ids_round_trip() -> None:
    for key_id in range(1, 25):
        key = key_from_id(key_id)
        assert key is not None and key_to_id(key) == key_id


def test_key_map_matches_mixxx() -> None:
    # A blob Mixxx 2.5.6 wrote for E minor (2m) read from tags (source 1).
    assert encode_key_map(17, "2m", source=1) == bytes.fromhex("08111202326D2001")
