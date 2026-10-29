"""Typed access to service JSON, which comes in as untyped dicts and lists."""

from typing import Any, cast


def obj(value: object) -> dict[str, Any]:
    """``value`` as a JSON object, or an empty one."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def objects(value: object) -> list[dict[str, Any]]:
    """``value`` as a list of JSON objects; anything else is skipped."""
    if not isinstance(value, list):
        return []
    items: list[object] = cast("list[object]", value)
    mapped = [obj(item) for item in items]
    return [m for m, item in zip(mapped, items, strict=True) if m is item]  # dicts only


def text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
