"""Turning playlist and folder names into file names valid on Windows, macOS and Linux."""

import re

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)
MAX_NAME_BYTES = 150


def sanitize(name: str) -> str:
    cleaned = _INVALID.sub("_", name).rstrip(" .")
    cleaned = _truncate(cleaned).rstrip(" .") or "_"
    base, dot, rest = cleaned.partition(".")
    if base.upper() in _RESERVED:
        cleaned = f"{base}_{dot}{rest}"
    return cleaned


def unique(name: str, taken: set[str]) -> str:
    """``name``, or ``name (2)``, ``name (3)``... so it is not in ``taken`` (case-insensitive).

    The chosen name is added to ``taken``.
    """
    candidate, counter = name, 2
    while candidate.casefold() in taken:
        suffix = f" ({counter})"
        candidate = _truncate(name, MAX_NAME_BYTES - len(suffix.encode())) + suffix
        counter += 1
    taken.add(candidate.casefold())
    return candidate


def _truncate(text: str, limit: int = MAX_NAME_BYTES) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore")
