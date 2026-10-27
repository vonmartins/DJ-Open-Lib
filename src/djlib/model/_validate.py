"""Shared validation helpers for model entities."""

import math
import re

from djlib.model.errors import ValidationError

_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def set_field(obj: object, name: str, value: object) -> None:
    """Assign a normalized value to a field of a frozen dataclass during ``__post_init__``."""
    object.__setattr__(obj, name, value)


def check_int(
    entity: str,
    field: str,
    value: int | None,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    required: bool = False,
) -> None:
    """Require an ``int`` (not ``bool``) within the bounds; ``None`` passes unless required."""
    if value is None:
        if required:
            raise ValidationError(entity, field, "is required")
        return
    if type(value) is not int:
        raise ValidationError(entity, field, "must be an integer")
    if minimum is not None and value < minimum:
        raise ValidationError(entity, field, f"must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValidationError(entity, field, f"must be at most {maximum}")


def check_positive_float(entity: str, field: str, value: float | None) -> float | None:
    """Require ``value`` to be ``None`` or a finite number greater than 0; return it as float."""
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValidationError(entity, field, "must be a number")
    if not math.isfinite(value) or value <= 0:
        raise ValidationError(entity, field, "must be a finite number greater than 0")
    return float(value)


def check_color(entity: str, field: str, value: str | None) -> str | None:
    """Require ``value`` to be ``None`` or ``#RRGGBB``; return it upper-cased."""
    if value is None:
        return None
    if not isinstance(value, str) or not _COLOR.match(value):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValidationError(entity, field, "must be a color in #RRGGBB form")
    return value.upper()


def check_text(entity: str, field: str, value: str | None) -> None:
    """Require ``value`` to be ``None`` or a string."""
    if value is not None and not isinstance(value, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValidationError(entity, field, "must be text")
