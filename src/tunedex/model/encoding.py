"""Canonical JSON for model values, shared by plans, fingerprints and merge bases."""

import dataclasses
import datetime
import enum
import uuid
from collections.abc import Mapping, Sequence
from pathlib import PurePath
from typing import cast

from tunedex.model.key import Key
from tunedex.model.unmapped import JSONValue


def to_json(value: object) -> JSONValue:
    """A model value as JSON: keys in both notations, dates as ISO text, times in µs."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Key):
        return {"open_key": value.open_key(), "musical": value.musical()}
    if isinstance(value, datetime.date):  # datetimes included
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return to_json(value.value)
    if isinstance(value, uuid.UUID | PurePath):
        return str(value)
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {str(k): to_json(v) for k, v in mapping.items()}
    if isinstance(value, tuple | list):
        return [to_json(item) for item in cast("Sequence[object]", value)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    raise TypeError(f"cannot convert {type(value).__name__} to JSON")
