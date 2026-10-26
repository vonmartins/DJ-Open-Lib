"""Format-specific data the model does not understand, kept for lossless round-trips."""

import math
from collections.abc import Mapping
from typing import TypeAlias, cast

from djlib.model.errors import ValidationError

JSONValue: TypeAlias = bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"] | None
Unmapped: TypeAlias = Mapping[str, JSONValue]


def copy_unmapped(value: Mapping[str, object], *, entity: str) -> dict[str, JSONValue]:
    """Validate ``value`` as ``{format name: JSON data}`` and return a detached copy.

    Tuples are accepted and copied as lists. Anything that JSON cannot represent
    exactly (non-string keys, NaN, infinity, other types) is rejected.
    """
    result: dict[str, JSONValue] = {}
    for name, data in value.items():
        if not isinstance(name, str) or not name:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError(entity, "unmapped", "format names must be non-empty strings")
        result[name] = copy_json(data, entity=entity, field="unmapped", where=name)
    return result


def copy_json(value: object, *, entity: str, field: str, where: str) -> JSONValue:
    """Validate ``value`` as JSON data and return a detached copy (tuples become lists)."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError(entity, field, f"{where}: NaN and infinity are not JSON")
        return value
    if isinstance(value, list | tuple):
        items = cast("list[object] | tuple[object, ...]", value)
        return [
            copy_json(x, entity=entity, field=field, where=f"{where}[{i}]")
            for i, x in enumerate(items)
        ]
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        copied: dict[str, JSONValue] = {}
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise ValidationError(entity, field, f"{where}: object keys must be strings")
            copied[key] = copy_json(item, entity=entity, field=field, where=f"{where}.{key}")
        return copied
    raise ValidationError(entity, field, f"{where}: {type(value).__name__} is not JSON")
