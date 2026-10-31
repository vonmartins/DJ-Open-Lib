"""Rules files: which bundled fixes run, with which options, and the user's own rules.

```yaml
fixes:
  fix_case: {keep: [DJ, MC]}   # enable and tune
  extract_featured: false      # disable
rules:
  - id: no-year
    when: {field: title, op: matches, value: ' \\[\\d{4}\\]$'}
    then: {replace: title, pattern: ' \\[\\d{4}\\]$', with: ''}
rename:
  pattern: '{artist} - {title}'   # file names for tunedex rename
```

Every error is collected with the fix name or rule it belongs to, and reported together.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from tunedex.model.playlist import MatchMode
from tunedex.renaming import Pattern, PatternError, parse_pattern
from tunedex.rules.conditions import Condition, field_kind, from_mapping
from tunedex.rules.errors import RuleError
from tunedex.rules.fixes import BY_NAME, FIXES, Fix, fix_options


@dataclass(frozen=True, slots=True)
class Replace:
    field: str
    pattern: re.Pattern[str]
    replacement: str


@dataclass(frozen=True, slots=True)
class Set:
    field: str
    value: Any
    """As written; checked against the field when applied."""


Action = Replace | Set


@dataclass(frozen=True, slots=True)
class UserRule:
    id: str
    conditions: tuple[Condition, ...]
    match: MatchMode
    actions: tuple[Action, ...]


@dataclass(frozen=True, slots=True)
class RuleSet:
    fixes: tuple[tuple[Fix, Mapping[str, Any]], ...]
    rules: tuple[UserRule, ...]
    rename: Pattern | None = None
    """The file name pattern of ``tunedex rename``, when the rules file sets one."""

    @property
    def names(self) -> tuple[str, ...]:
        return (*(fix.name for fix, _ in self.fixes), *(rule.id for rule in self.rules))

    def only(self, names: Iterable[str]) -> "RuleSet":
        """The fixes and rules named in ``names``; unknown names are an error."""
        wanted = list(dict.fromkeys(names))
        known = {*BY_NAME, *(rule.id for rule in self.rules)}
        unknown = [name for name in wanted if name not in known]
        if unknown:
            raise RuleError(f"unknown fixes or rules: {', '.join(unknown)}")
        chosen = set(wanted)
        fixes = [(fix, options) for fix, options in self.fixes if fix.name in chosen]
        for name in wanted:  # a fix that is off by default runs when named
            if name in BY_NAME and all(fix.name != name for fix, _ in fixes):
                fixes.append((BY_NAME[name], fix_options(BY_NAME[name], None)))
        order = {fix.name: index for index, fix in enumerate(FIXES)}
        fixes.sort(key=lambda item: order[item[0].name])
        rules = tuple(rule for rule in self.rules if rule.id in chosen)
        return RuleSet(fixes=tuple(fixes), rules=rules, rename=self.rename)


def defaults() -> RuleSet:
    """The bundled fixes that are on by default, with their default options."""
    return RuleSet(fixes=tuple((f, fix_options(f, None)) for f in FIXES if f.on), rules=())


def load(path: Path) -> RuleSet:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RuleError(f"cannot read {path}: {error}") from error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise RuleError(f"{path} is not valid YAML: {error}") from error
    return parse(data, origin=str(path))


def _mapping(value: object) -> dict[str, Any] | None:
    """A YAML mapping with text keys, or ``None`` when ``value`` is not one."""
    if not isinstance(value, dict):
        return None
    return {str(k): v for k, v in cast("dict[Any, Any]", value).items()}


def _list(value: object) -> list[Any] | None:
    return list(cast("list[Any]", value)) if isinstance(value, list) else None


def parse(data: Any, *, origin: str = "rules") -> RuleSet:
    """A rule set from parsed YAML; every problem is reported in one error."""
    errors: list[str] = []
    mapping = {} if data is None else _mapping(data)
    if mapping is None:
        raise RuleError(f"{origin}: expected a mapping with `fixes`, `rules` and `rename`")
    unknown = set(mapping) - {"fixes", "rules", "rename"}
    if unknown:
        errors.append(f"unknown sections: {', '.join(sorted(unknown))}")
    fixes = _fixes({} if mapping.get("fixes") is None else mapping["fixes"], errors)
    rules = _rules([] if mapping.get("rules") is None else mapping["rules"], errors)
    rename = None if mapping.get("rename") is None else _rename(mapping["rename"], errors)
    if errors:
        raise RuleError(f"{origin}:\n" + "\n".join(f"  {e}" for e in errors))
    return RuleSet(fixes=fixes, rules=rules, rename=rename)


def _rename(data: Any, errors: list[str]) -> Pattern | None:
    settings = _mapping(data)
    if settings is None or set(settings) != {"pattern"} or not isinstance(settings["pattern"], str):
        errors.append(
            "rename: expected a mapping with a pattern, such as {pattern: '{artist} - {title}'}"
        )
        return None
    try:
        return parse_pattern(settings["pattern"])
    except PatternError as error:
        errors.append(f"rename: {error}")
        return None


def _fixes(data: Any, errors: list[str]) -> tuple[tuple[Fix, Mapping[str, Any]], ...]:
    settings = _mapping(data)
    if settings is None:
        errors.append("fixes: expected a mapping of fix names")
        settings = {}
    for name in settings:
        if name not in BY_NAME:
            errors.append(f"fixes.{name}: unknown fix (known: {', '.join(BY_NAME)})")
    chosen: list[tuple[Fix, Mapping[str, Any]]] = []
    for fix in FIXES:
        setting = settings.get(fix.name, fix.on)
        if setting is False or (setting is None and not fix.on):
            continue
        options = {} if setting is True or setting is None else _mapping(setting)
        if options is None:
            errors.append(f"fixes.{fix.name}: expected true, false or options")
            continue
        try:
            chosen.append((fix, fix_options(fix, options)))
        except RuleError as error:
            errors.append(f"fixes.{error}")
    return tuple(chosen)


def _rules(data: Any, errors: list[str]) -> tuple[UserRule, ...]:
    items = _list(data)
    if items is None:
        errors.append("rules: expected a list")
        return ()
    rules: list[UserRule] = []
    seen: set[str] = set()
    for index, raw in enumerate(items):
        label = f"rules[{index}]"
        try:
            rule = _rule(raw, label)
        except RuleError as error:
            errors.append(str(error))
            continue
        if rule.id in seen or rule.id in BY_NAME:
            errors.append(f"{label} ({rule.id}): the id is already used")
            continue
        seen.add(rule.id)
        rules.append(rule)
    return tuple(rules)


def _rule(value: object, label: str) -> UserRule:
    raw = _mapping(value)
    if raw is None:
        raise RuleError(f"{label}: expected a mapping with id, when and then")
    rule_id = raw.get("id")
    if isinstance(rule_id, str) and rule_id:
        label = f"{label} ({rule_id})"
    else:
        raise RuleError(f"{label}: needs an id")
    unknown = set(raw) - {"id", "when", "match", "then"}
    if unknown:
        raise RuleError(f"{label}: unknown keys {', '.join(sorted(unknown))}")
    try:
        match = MatchMode(raw.get("match", "all"))
    except ValueError:
        raise RuleError(f"{label}: match must be all or any") from None
    when, then = raw.get("when", []), raw.get("then")
    when_list: list[Any] | None = [when] if isinstance(when, dict) else _list(when)
    if when_list is None:
        raise RuleError(f"{label}: when must be a condition or a list of them")
    then_list: list[Any] | None = [then] if isinstance(then, dict) else _list(then)
    if not then_list:
        raise RuleError(f"{label}: then must be an action or a list of them")
    try:
        conditions = tuple(from_mapping(_mapping(c) or {}) for c in when_list)
        actions = tuple(_action(a) for a in then_list)
    except RuleError as error:
        raise RuleError(f"{label}: {error}") from None
    return UserRule(id=rule_id, conditions=conditions, match=match, actions=actions)


def _action(value: object) -> Action:
    raw = _mapping(value)
    if raw is None:
        raise RuleError("an action must be a mapping")
    keys = set(raw)
    if "replace" in keys:
        unknown = keys - {"replace", "pattern", "with"}
        if unknown:
            raise RuleError(f"unknown action keys {', '.join(sorted(unknown))}")
        field, pattern, replacement = raw["replace"], raw.get("pattern"), raw.get("with", "")
        if not isinstance(field, str) or field_kind(field) != "text":
            raise RuleError(f"replace works on text fields, not {field!r}")
        if not isinstance(pattern, str):
            raise RuleError("replace needs a pattern")
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            raise RuleError(f"invalid regular expression {pattern!r} ({error})") from None
        return Replace(field, compiled, str(replacement or ""))
    if "set" in keys:
        unknown = keys - {"set", "value"}
        if unknown:
            raise RuleError(f"unknown action keys {', '.join(sorted(unknown))}")
        field = raw["set"]
        if not isinstance(field, str):
            raise RuleError("set needs a field name")
        field_kind(field)
        return Set(field, raw.get("value"))
    raise RuleError("an action needs replace or set")
