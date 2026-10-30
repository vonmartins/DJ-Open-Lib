import datetime

import pytest

from djlib.model.key import parse_open_key
from djlib.model.track import Track
from djlib.query import parse_where
from djlib.rules import RuleError


def track(**fields: object) -> Track:
    return Track(path_origin="/music/a.mp3", **fields)  # pyright: ignore[reportArgumentType]


def test_text_contains_ignores_case() -> None:
    where = parse_where("title ~ remix")

    assert where.holds(track(title="Storm (Mira Remix)"))
    assert not where.holds(track(title="Storm"))


def test_number_range() -> None:
    low, high = parse_where("bpm>=170"), parse_where("bpm<180")

    assert [
        bpm
        for bpm in (169.9, 170, 175.5, 180)
        if low.holds(track(bpm=bpm)) and high.holds(track(bpm=bpm))
    ] == [170, 175.5]


def test_operators() -> None:
    assert parse_where("genre=techno").holds(track(genre="Techno"))
    assert parse_where("genre!=House").holds(track(genre="Techno"))
    assert parse_where("genre!~hou").holds(track(genre="Techno"))
    assert parse_where("year>2000").holds(track(year=2001))
    assert parse_where("year<=2000").holds(track(year=2000))


def test_empty_and_not_empty() -> None:
    assert parse_where("genre=").holds(track())
    assert not parse_where("genre=").holds(track(genre="Techno"))
    assert parse_where("genre!=").holds(track(genre="Techno"))


def test_dates_keys_and_tags() -> None:
    assert parse_where("date_added>=2026-01-01").holds(track(date_added=datetime.date(2026, 3, 1)))
    assert parse_where("key=1m").holds(track(key=parse_open_key("1m")))
    assert parse_where("key=Am").holds(track(key=parse_open_key("1m")))
    assert parse_where("tags=warmup").holds(track(tags=("Warmup",)))
    assert parse_where("tags!=peak").holds(track(tags=("Warmup",)))


def test_operator_in_the_value_is_kept() -> None:
    where = parse_where("title~a=b")

    assert (where.op, where.values) == ("contains", ("a=b",))


@pytest.mark.parametrize("text", ["gnre=Techno", "bpm>fast", "title>a", "genre", "=x", "key=H"])
def test_invalid_expressions_name_the_expression(text: str) -> None:
    with pytest.raises(RuleError, match=f"'{text}'"):
        parse_where(text)
