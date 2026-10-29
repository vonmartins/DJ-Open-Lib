"""Running a rule set on a track: the enabled fixes, then the user's rules."""

import dataclasses
from dataclasses import dataclass
from typing import Any

from djlib.model.errors import ValidationError
from djlib.model.track import Track
from djlib.rules.conditions import date_value, field_kind, holds, key_value
from djlib.rules.errors import RuleError
from djlib.rules.fixes import run_fixes
from djlib.rules.ruleset import Replace, RuleSet, Set


@dataclass(frozen=True, slots=True)
class Edit:
    """One field's value before and after, and the fixes or rules that changed it."""

    field: str
    before: Any
    after: Any
    by: str


def run(ruleset: RuleSet, track: Track) -> tuple[Track, list[Edit], list[str]]:
    """The track after ``ruleset``, its field edits, and warnings for rules that did not fit."""
    original = track
    warnings: list[str] = []
    track, applied = run_fixes(track, ruleset.fixes)
    touched: dict[str, list[str]] = {}
    for name, _value, by in applied:
        touched.setdefault(name, []).append(by)
    for rule in ruleset.rules:
        if not holds(rule.conditions, rule.match, track):
            continue
        changes: dict[str, Any] = {}
        current = track
        try:
            for action in rule.actions:
                value = _action_value(action, current)
                changes[action.field] = value
                current = dataclasses.replace(current, **{action.field: value})
        except (RuleError, ValidationError) as error:
            warnings.append(f"{track.path}: rule {rule.id} not applied ({error})")
            continue
        for name, value in changes.items():
            if getattr(track, name) != value:
                touched.setdefault(name, []).append(rule.id)
        track = current
    edits = [
        Edit(name, getattr(original, name), getattr(track, name), ", ".join(dict.fromkeys(by)))
        for name, by in touched.items()
        if getattr(original, name) != getattr(track, name)
    ]
    return track, edits, warnings


def _action_value(action: Replace | Set, track: Track) -> Any:
    if isinstance(action, Replace):
        text = getattr(track, action.field)
        if not isinstance(text, str):
            return text
        replaced = action.pattern.sub(action.replacement, text).strip()
        return replaced or None
    return _value(action.field, action.value)


def _value(field: str, value: Any) -> Any:
    """``value`` as written in YAML, as the field's type; empty values clear the field."""
    if value is None or value == "" or value == []:
        return () if field == "tags" else None
    kind = field_kind(field)
    if kind == "text":
        return str(value)
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise RuleError(f"{field} needs a number, not {value!r}")
        return value
    if kind in ("date", "datetime"):
        return date_value(field, kind, value)
    if kind == "key":
        key = key_value(value)
        if key is None:
            raise RuleError(f"{field} needs a key such as 1m or Am, not {value!r}")
        return key
    if not isinstance(value, list):
        raise RuleError(f"{field} needs a list")
    return tuple(str(v) for v in value)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
