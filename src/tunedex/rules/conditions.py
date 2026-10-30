"""Conditions on tracks: ``{field, op, value}``, as smartlists and rules use them.

Text comparisons other than ``matches`` ignore case. A condition on an empty field is
false for every operator except ``empty``, ``not_equals`` and ``not_contains``.
"""

import datetime
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tunedex.model.key import Key, parse_musical, parse_open_key
from tunedex.model.playlist import MatchMode, Rule
from tunedex.model.track import DATE_FIELDS, INT_FIELDS, TEXT_FIELDS, Track
from tunedex.model.unmapped import JSONValue
from tunedex.rules.errors import RuleError

TEXT_OPERATORS = frozenset(
    {
        "equals",
        "not_equals",
        "contains",
        "not_contains",
        "starts_with",
        "ends_with",
        "in",
        "matches",
        "empty",
        "not_empty",
    }
)
ORDER_OPERATORS = frozenset(
    {"equals", "not_equals", "gt", "gte", "lt", "lte", "in", "empty", "not_empty"}
)
SET_OPERATORS = frozenset({"equals", "not_equals", "in", "empty", "not_empty"})
LIST_OPERATORS = frozenset({"contains", "not_contains", "empty", "not_empty"})
_NO_VALUE = frozenset({"empty", "not_empty"})
_TRUE_WHEN_EMPTY = frozenset({"empty", "not_equals", "not_contains"})

_NUMBER_FIELDS = frozenset({*INT_FIELDS, "bpm"})
_DATE_FIELDS = frozenset(DATE_FIELDS)
_DATETIME_FIELDS = frozenset({"last_played"})
_TEXT_FIELDS = frozenset({*TEXT_FIELDS, "path", "color"})


def field_kind(name: str) -> str:
    """``text``, ``number``, ``date``, ``datetime``, ``key`` or ``list``; unknown fields raise."""
    if name in _TEXT_FIELDS:
        return "text"
    if name in _NUMBER_FIELDS:
        return "number"
    if name in _DATE_FIELDS:
        return "date"
    if name in _DATETIME_FIELDS:
        return "datetime"
    if name == "key":
        return "key"
    if name == "tags":
        return "list"
    raise RuleError(f"unknown field {name!r}")


_OPERATORS = {
    "text": TEXT_OPERATORS,
    "number": ORDER_OPERATORS,
    "date": ORDER_OPERATORS,
    "datetime": ORDER_OPERATORS,
    "key": SET_OPERATORS,
    "list": LIST_OPERATORS,
}


@dataclass(frozen=True, slots=True)
class Condition:
    field: str
    op: str
    values: tuple[Any, ...] = ()
    """Values converted to the field's type (numbers, dates, keys, compiled patterns)."""

    def holds(self, track: Track) -> bool:
        value = getattr(track, self.field)
        if value is None or value == "" or value == ():
            return self.op in _TRUE_WHEN_EMPTY
        if self.op == "empty":
            return False
        if self.op == "not_empty":
            return True
        kind = field_kind(self.field)
        if kind == "list":
            tags = {str(t).casefold() for t in value}
            found = any(str(v).casefold() in tags for v in self.values)
            return found if self.op == "contains" else not found
        if kind == "text":
            return _text_holds(self.op, str(value), self.values)
        return _value_holds(self.op, value, self.values)


def _text_holds(op: str, value: str, values: Sequence[Any]) -> bool:
    if op == "matches":
        return any(pattern.search(value) for pattern in values)
    folded = value.casefold()
    wanted = [str(v).casefold() for v in values]
    match op:
        case "equals" | "in":
            return folded in wanted
        case "not_equals":
            return folded not in wanted
        case "contains":
            return any(w in folded for w in wanted)
        case "not_contains":
            return not any(w in folded for w in wanted)
        case "starts_with":
            return any(folded.startswith(w) for w in wanted)
        case "ends_with":
            return any(folded.endswith(w) for w in wanted)
        case _:
            raise RuleError(f"operator {op!r} does not apply to text")


def _value_holds(op: str, value: Any, values: Sequence[Any]) -> bool:
    match op:
        case "equals" | "in":
            return value in values
        case "not_equals":
            return value not in values
        case "gt":
            return value > values[0]
        case "gte":
            return value >= values[0]
        case "lt":
            return value < values[0]
        case "lte":
            return value <= values[0]
        case _:
            raise RuleError(f"operator {op!r} does not apply here")


def condition(field: str, op: str, values: Iterable[JSONValue] = ()) -> Condition:
    """Build a checked condition from raw values (as written in YAML or stored in a Rule)."""
    kind = field_kind(field)
    if op not in _OPERATORS[kind]:
        allowed = ", ".join(sorted(_OPERATORS[kind]))
        raise RuleError(f"operator {op!r} does not apply to {field} (use one of: {allowed})")
    raw = list(values)
    if op in _NO_VALUE:
        if raw:
            raise RuleError(f"operator {op!r} takes no value")
        return Condition(field, op)
    if not raw:
        raise RuleError(f"operator {op!r} on {field} needs a value")
    if op in {"gt", "gte", "lt", "lte"} and len(raw) != 1:
        raise RuleError(f"operator {op!r} takes one value")
    return Condition(field, op, tuple(_convert(field, kind, op, v) for v in raw))


def _convert(field: str, kind: str, op: str, value: JSONValue) -> Any:
    if kind in ("text", "list"):
        if not isinstance(value, str | int | float) or isinstance(value, bool):
            raise RuleError(f"{field}: expected text, got {value!r}")
        if op == "matches":
            try:
                return re.compile(str(value))
            except re.error as error:
                raise RuleError(
                    f"{field}: invalid regular expression {value!r} ({error})"
                ) from None
        return str(value)
    if kind == "number":
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise RuleError(f"{field}: expected a number, got {value!r}")
        return value
    if kind in ("date", "datetime"):
        return date_value(field, kind, value)
    key = key_value(value)
    if key is None:
        raise RuleError(f"{field}: expected a key such as 1m or Am, got {value!r}")
    return key


def key_value(value: object) -> Key | None:
    if not isinstance(value, str):
        return None
    return parse_open_key(value) or parse_musical(value)


def date_value(field: str, kind: str, value: object) -> datetime.date:
    """An ISO date text, or a date YAML already parsed, as the field's type."""
    if isinstance(value, datetime.datetime):
        moment = value
    elif isinstance(value, datetime.date):
        moment = datetime.datetime.combine(value, datetime.time())
    elif isinstance(value, str):
        try:
            moment = datetime.datetime.fromisoformat(value)
        except ValueError:
            raise RuleError(f"{field}: expected an ISO date, got {value!r}") from None
    else:
        raise RuleError(f"{field}: expected an ISO date, got {value!r}")
    if kind == "date":
        return moment.date()
    return moment if moment.tzinfo else moment.replace(tzinfo=datetime.UTC)


def from_mapping(data: Mapping[str, Any]) -> Condition:
    """A condition written as ``{field, op, value}`` or ``{field, op, values}``."""
    unknown = set(data) - {"field", "op", "value", "values"}
    if unknown:
        raise RuleError(f"unknown condition keys: {', '.join(sorted(unknown))}")
    field, op = data.get("field"), data.get("op")
    if not isinstance(field, str) or not isinstance(op, str):
        raise RuleError("a condition needs a field and an op")
    if "value" in data and "values" in data:
        raise RuleError("a condition takes value or values, not both")
    if "values" in data:
        values = data["values"]
        if not isinstance(values, list):
            raise RuleError("values must be a list")
    else:
        values = [] if "value" not in data else [data["value"]]
    return condition(field, op, values)  # pyright: ignore[reportUnknownArgumentType]


def holds(conditions: Sequence[Condition], match: MatchMode, track: Track) -> bool:
    """Whether ``conditions`` hold for ``track``; no conditions always hold."""
    if not conditions:
        return True
    results = (c.holds(track) for c in conditions)
    return all(results) if match is MatchMode.ALL else any(results)


def from_rule(rule: Rule) -> Condition:
    """The condition a smartlist ``Rule`` stores."""
    return condition(rule.field, rule.operator, rule.values)
