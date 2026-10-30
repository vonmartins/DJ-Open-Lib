import math

import pytest

from tunedex.model.errors import ValidationError
from tunedex.model.unmapped import copy_unmapped


def test_nested_data_is_kept() -> None:
    data = {"traktor": {"LOCK": "1", "flags": [1, 2.5, True, None, {"x": "y"}]}}

    assert copy_unmapped(data, entity="Track") == data


def test_tuples_become_lists() -> None:
    assert copy_unmapped({"m3u": {"lines": ("a", "b")}}, entity="Track") == {
        "m3u": {"lines": ["a", "b"]}
    }


def test_copy_is_detached_from_caller() -> None:
    inner = {"LOCK": "1"}
    data = {"traktor": inner}

    copied = copy_unmapped(data, entity="Track")
    inner["LOCK"] = "0"

    assert copied == {"traktor": {"LOCK": "1"}}


@pytest.mark.parametrize(
    "data",
    [
        {"traktor": math.nan},
        {"traktor": [math.inf]},
        {"traktor": {1: "a"}},
        {"traktor": {"when": object()}},
        {"traktor": {b"raw"}},
        {"": {}},
        {1: {}},
    ],
)
def test_rejects_non_json(data: dict[object, object]) -> None:
    with pytest.raises(ValidationError) as excinfo:
        copy_unmapped(data, entity="Cue")  # pyright: ignore[reportArgumentType]

    assert (excinfo.value.entity, excinfo.value.field) == ("Cue", "unmapped")
