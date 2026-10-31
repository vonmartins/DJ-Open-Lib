"""Conditions on tracks (specs/rules-engine)."""

import datetime
import re

import pytest

from tunedex.model.key import Key, Mode
from tunedex.model.playlist import MatchMode, Rule
from tunedex.model.track import Track
from tunedex.rules import RuleError
from tunedex.rules.conditions import condition, from_mapping, from_rule, holds

TRACK = Track(
    path_origin="/music/Drum/Glue.mp3",
    title="Glue [2016]",
    artist="Bicep",
    genre="Drum And Bass",
    bpm=128.0,
    year=2016,
    key=Key(tonic=9, mode=Mode.MINOR),
    date_added=datetime.date(2026, 2, 20),
    last_played=datetime.datetime(2026, 3, 1, 22, 0, tzinfo=datetime.UTC),
    tags=("Peak", "Dark"),
)
EMPTY = Track(path_origin="/music/empty.mp3")


@pytest.mark.parametrize(
    ("field", "op", "values", "expected"),
    [
        ("genre", "contains", ["drum"], True),
        ("genre", "not_contains", ["house"], True),
        ("genre", "equals", ["drum and bass"], True),
        ("genre", "not_equals", ["Drum And Bass"], False),
        ("genre", "starts_with", ["DRUM"], True),
        ("genre", "ends_with", ["bass"], True),
        ("genre", "in", ["House", "Drum And Bass"], True),
        ("title", "matches", [r"\[\d{4}\]$"], True),
        ("title", "matches", [r"^glue"], False),  # regexes keep their case
        ("path", "contains", ["/drum/"], True),
        ("bpm", "gt", [127.5], True),
        ("bpm", "gte", [128], True),
        ("bpm", "lt", [128], False),
        ("bpm", "lte", [128], True),
        ("year", "equals", [2016], True),
        ("year", "in", [2015, 2017], False),
        ("date_added", "gte", ["2026-01-01"], True),
        ("date_added", "lt", [datetime.date(2026, 2, 20)], False),
        ("last_played", "gt", ["2026-03-01T21:00:00+00:00"], True),
        ("key", "equals", ["1m"], True),
        ("key", "in", ["Am", "C"], True),
        ("key", "not_equals", ["8d"], True),
        ("tags", "contains", ["peak"], True),
        ("tags", "not_contains", ["Warm"], True),
        ("genre", "not_empty", [], True),
        ("genre", "empty", [], False),
    ],
)
def test_operators(field: str, op: str, values: list[object], expected: bool) -> None:
    assert condition(field, op, values).holds(TRACK) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "op", "values", "expected"),
    [
        ("bpm", "lt", [100], False),
        ("bpm", "not_equals", [128], True),
        ("genre", "contains", ["drum"], False),
        ("genre", "not_contains", ["drum"], True),
        ("genre", "empty", [], True),
        ("genre", "not_empty", [], False),
        ("title", "matches", [".*"], False),
        ("key", "equals", ["1m"], False),
        ("tags", "empty", [], True),
        ("date_added", "gt", ["2000-01-01"], False),
    ],
)
def test_empty_field(field: str, op: str, values: list[object], expected: bool) -> None:
    assert condition(field, op, values).holds(EMPTY) is expected  # type: ignore[arg-type]


def test_unicode_values() -> None:
    track = Track(path_origin="/m/a.mp3", artist="Röyksopp", title="Пример", genre="Música")

    assert condition("artist", "equals", ["RÖYKSOPP"]).holds(track)
    assert condition("title", "contains", ["пример"]).holds(track)
    assert condition("genre", "matches", ["^Mús"]).holds(track)


def test_all_and_any() -> None:
    drum = condition("genre", "contains", ["drum"])
    slow = condition("bpm", "lt", [100])

    assert holds([drum, slow], MatchMode.ANY, TRACK)
    assert not holds([drum, slow], MatchMode.ALL, TRACK)
    assert holds([], MatchMode.ALL, TRACK)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"field": "titel", "op": "equals", "value": "x"}, "unknown field 'titel'"),
        ({"field": "title", "op": "gt", "value": "x"}, "operator 'gt' does not apply to title"),
        ({"field": "bpm", "op": "contains", "value": 1}, "does not apply to bpm"),
        ({"field": "title", "op": "matches", "value": "("}, "invalid regular expression"),
        ({"field": "bpm", "op": "gt", "value": "fast"}, "expected a number"),
        ({"field": "bpm", "op": "gt", "values": [1, 2]}, "takes one value"),
        ({"field": "year", "op": "equals"}, "needs a value"),
        ({"field": "year", "op": "empty", "value": 1}, "takes no value"),
        ({"field": "date_added", "op": "gt", "value": "yesterday"}, "expected an ISO date"),
        ({"field": "key", "op": "equals", "value": "H minor"}, "expected a key"),
        ({"field": "title", "op": "equals", "value": "x", "values": ["y"]}, "not both"),
        ({"field": "title", "op": "equals", "valeu": "x"}, "unknown condition keys"),
        ({"op": "equals", "value": "x"}, "needs a field and an op"),
    ],
)
def test_invalid_conditions(data: dict[str, object], message: str) -> None:
    with pytest.raises(RuleError, match=re.escape(message)):
        from_mapping(data)


def test_smartlist_rules() -> None:
    rule = Rule(field="genre", operator="contains", values=("Drum",))

    assert from_rule(rule).holds(TRACK)
