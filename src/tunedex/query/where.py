"""Where expressions: ``FIELD OP VALUE`` filters such as ``bpm>=170`` or ``title~remix``."""

import re

from tunedex.model.unmapped import JSONValue
from tunedex.rules.conditions import Condition, condition, field_kind
from tunedex.rules.errors import RuleError

# Longest operators first, so that ``>=`` is not read as ``>`` followed by ``=value``.
_OPERATORS = {
    "!=": "not_equals",
    "!~": "not_contains",
    ">=": "gte",
    "<=": "lte",
    "=": "equals",
    "~": "contains",
    ">": "gt",
    "<": "lt",
}
_EXPRESSION = re.compile(
    r"\s*(?P<field>[a-z_0-9]+)\s*(?P<op>!=|!~|>=|<=|=|~|>|<)(?P<value>.*)", re.DOTALL
)
_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)")


def parse_where(text: str) -> Condition:
    """The condition ``text`` describes; ``RuleError`` naming ``text`` when it is not valid.

    ``FIELD=`` with no value matches an empty field and ``FIELD!=`` a field with a value.
    On tags, ``=`` and ``!=`` mean contains and does not contain.
    """
    found = _EXPRESSION.fullmatch(text)
    if found is None:
        raise RuleError(f"{text!r}: expected FIELD OP VALUE, such as genre=Techno or bpm>=170")
    field, symbol, value = found["field"], found["op"], found["value"].strip()
    try:
        kind = field_kind(field)
        op = _OPERATORS[symbol]
        if not value and symbol in ("=", "!="):
            return condition(field, "empty" if symbol == "=" else "not_empty")
        if kind == "list" and symbol in ("=", "!="):
            op = "contains" if symbol == "=" else "not_contains"
        return condition(field, op, [_value(kind, value)])
    except RuleError as error:
        raise RuleError(f"{text!r}: {error}") from None


def _value(kind: str, value: str) -> JSONValue:
    if kind != "number":
        return value
    if not _NUMBER.fullmatch(value):
        raise RuleError(f"expected a number, got {value!r}")
    number = float(value)
    return int(number) if number.is_integer() and "." not in value else number
