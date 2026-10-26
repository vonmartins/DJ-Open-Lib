import pytest

from djlib.model.errors import ValidationError
from djlib.model.ids import new_node_id, new_track_id


def test_validation_error_carries_fields() -> None:
    error = ValidationError("Track", "rating", "must be between 0 and 5")

    assert error.entity == "Track"
    assert error.field == "rating"
    assert error.message == "must be between 0 and 5"
    assert str(error) == "Track.rating: must be between 0 and 5"


def test_validation_error_is_a_value_error() -> None:
    with pytest.raises(ValueError):
        raise ValidationError("Track", "bpm", "must be positive")


def test_track_ids_are_unique() -> None:
    assert len({new_track_id() for _ in range(10_000)}) == 10_000


def test_node_ids_are_unique() -> None:
    assert len({new_node_id() for _ in range(10_000)}) == 10_000
