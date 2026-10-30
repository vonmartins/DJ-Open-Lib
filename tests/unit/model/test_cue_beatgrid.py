import math

import pytest

from tunedex.model.beatgrid import BeatGrid, BeatMarker
from tunedex.model.cue import Cue, CueKind
from tunedex.model.errors import ValidationError


def field_of(excinfo: pytest.ExceptionInfo[ValidationError]) -> tuple[str, str]:
    return excinfo.value.entity, excinfo.value.field


# Time unit


def test_sub_millisecond_position_kept() -> None:
    assert Cue(kind=CueKind.HOT, start_us=1_234_567, slot=0).start_us == 1_234_567


def test_negative_start_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Cue(kind=CueKind.HOT, start_us=-1)
    assert field_of(excinfo) == ("Cue", "start_us")


@pytest.mark.parametrize("start", [1.5, True, "10"])
def test_start_must_be_integer(start: object) -> None:
    with pytest.raises(ValidationError):
        Cue(kind=CueKind.MEMORY, start_us=start)  # pyright: ignore[reportArgumentType]


# Cues and loops


def test_valid_loop() -> None:
    loop = Cue(kind=CueKind.LOOP, start_us=10_000_000, end_us=18_000_000, active=True)
    assert (loop.start_us, loop.end_us, loop.active) == (10_000_000, 18_000_000, True)


@pytest.mark.parametrize("end", [10_000_000, 9_999_999])
def test_loop_must_end_after_start(end: int) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Cue(kind=CueKind.LOOP, start_us=10_000_000, end_us=end)
    assert field_of(excinfo) == ("Cue", "end_us")


def test_loop_requires_end() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Cue(kind=CueKind.LOOP, start_us=0)
    assert field_of(excinfo) == ("Cue", "end_us")


@pytest.mark.parametrize("kind", [CueKind.HOT, CueKind.MEMORY])
def test_non_loop_with_end_rejected(kind: CueKind) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Cue(kind=kind, start_us=0, end_us=1_000)
    assert field_of(excinfo) == ("Cue", "end_us")


def test_non_loop_cannot_be_active() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Cue(kind=CueKind.HOT, start_us=0, active=True)
    assert field_of(excinfo) == ("Cue", "active")


def test_color_upper_cased_and_validated() -> None:
    assert Cue(kind=CueKind.HOT, start_us=0, color="#ff00aa").color == "#FF00AA"
    with pytest.raises(ValidationError) as excinfo:
        Cue(kind=CueKind.HOT, start_us=0, color="red")
    assert field_of(excinfo) == ("Cue", "color")


def test_negative_slot_rejected() -> None:
    with pytest.raises(ValidationError):
        Cue(kind=CueKind.HOT, start_us=0, slot=-1)


def test_cue_unmapped_kept() -> None:
    cue = Cue(kind=CueKind.MEMORY, start_us=0, unmapped={"traktor": {"TYPE": "3"}})
    assert cue.unmapped == {"traktor": {"TYPE": "3"}}


# Beatgrid


def test_tempo_change() -> None:
    grid = BeatGrid(
        markers=(
            BeatMarker(position_us=0, bpm=128.0),
            BeatMarker(position_us=60_000_000, bpm=130.0, beat=3),
        )
    )
    assert [(m.position_us, m.bpm, m.beat) for m in grid.markers] == [
        (0, 128.0, 1),
        (60_000_000, 130.0, 3),
    ]


@pytest.mark.parametrize("second", [0, -5])
def test_unordered_markers_rejected(second: int) -> None:
    with pytest.raises(ValidationError) as excinfo:
        BeatGrid(
            markers=(
                BeatMarker(position_us=0, bpm=128.0),
                BeatMarker(position_us=max(second, 0), bpm=128.0),
            )
        )
    assert field_of(excinfo) == ("BeatGrid", "markers")


def test_markers_list_is_stored_as_tuple() -> None:
    grid = BeatGrid(markers=[BeatMarker(position_us=0, bpm=120)])  # pyright: ignore[reportArgumentType]
    assert grid.markers == (BeatMarker(position_us=0, bpm=120.0),)
    assert isinstance(grid.markers[0].bpm, float)


def test_empty_grid_rejected() -> None:
    with pytest.raises(ValidationError):
        BeatGrid(markers=())


@pytest.mark.parametrize("bpm", [0, -120.0, math.nan, math.inf])
def test_bpm_must_be_positive_and_finite(bpm: float) -> None:
    with pytest.raises(ValidationError) as excinfo:
        BeatMarker(position_us=0, bpm=bpm)
    assert field_of(excinfo) == ("BeatMarker", "bpm")


@pytest.mark.parametrize("beat", [0, 5])
def test_beat_in_bar_range(beat: int) -> None:
    with pytest.raises(ValidationError) as excinfo:
        BeatMarker(position_us=0, bpm=128.0, beat=beat)
    assert field_of(excinfo) == ("BeatMarker", "beat")
