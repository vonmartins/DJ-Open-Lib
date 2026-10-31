"""File names from a pattern of fields, safe on Linux, macOS and Windows.

A pattern is text with placeholders. ``{artist}`` stands for a field. An optional part
holds literal text and exactly one field name, such as ``{ (remixer remix)}``, and is
left out when that field is empty. Patterns are not Python format strings: no
attribute access or format specs.
"""

import re
import unicodedata
from dataclasses import dataclass

from tunedex.model.track import TEXT_FIELDS, Track

DEFAULT_PATTERN = "{artist} - {title}"
FIELDS = frozenset({*TEXT_FIELDS, "year", "bpm", "key", "track_number"})
MAX_NAME_BYTES = 255

_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FORBIDDEN = re.compile(r'[/\\*?"<>|\x00-\x1f\x7f]')
_SPACES = re.compile(r" {2,}")
_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)),
     *(f"LPT{n}" for n in range(1, 10))}
)  # fmt: skip


class PatternError(ValueError):
    """A pattern that cannot be used: unknown fields, or broken braces."""


@dataclass(frozen=True, slots=True)
class _Field:
    name: str
    before: str = ""
    after: str = ""
    optional: bool = False


@dataclass(frozen=True, slots=True)
class Missing:
    """A track lacks ``field``, which the pattern needs."""

    field: str


@dataclass(frozen=True, slots=True)
class Pattern:
    text: str
    parts: tuple[str | _Field, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(part.name for part in self.parts if isinstance(part, _Field))

    def format(self, track: Track) -> str | Missing:
        """The name the pattern gives ``track``, before it is made safe."""
        pieces: list[str] = []
        for part in self.parts:
            if isinstance(part, str):
                pieces.append(part)
                continue
            value = field_text(track, part.name)
            if value is None:
                if part.optional:
                    continue
                return Missing(part.name)
            pieces.append(f"{part.before}{value}{part.after}")
        return "".join(pieces)


def parse_pattern(text: str) -> Pattern:
    """Parse ``text``; raise ``PatternError`` naming what is wrong."""
    parts: list[str | _Field] = []
    position = 0
    while position < len(text):
        opening, closing = text.find("{", position), text.find("}", position)
        if closing != -1 and (opening == -1 or closing < opening):
            raise PatternError(f"pattern {text!r}: '}}' without '{{'")
        if opening == -1:
            parts.append(text[position:])
            break
        if opening > position:
            parts.append(text[position:opening])
        end = text.find("}", opening)
        if end == -1:
            raise PatternError(f"pattern {text!r}: '{{' without '}}'")
        content = text[opening + 1 : end]
        if "{" in content:
            raise PatternError(f"pattern {text!r}: braces cannot be nested")
        parts.append(_placeholder(text, content))
        position = end + 1
    if not any(isinstance(part, _Field) for part in parts):
        raise PatternError(f"pattern {text!r} has no field")
    return Pattern(text, tuple(parts))


def _placeholder(pattern: str, content: str) -> _Field:
    if _IDENTIFIER.fullmatch(content):
        if content not in FIELDS:
            raise PatternError(
                f"pattern {pattern!r}: unknown field {content!r}"
                f" (known: {', '.join(sorted(FIELDS))})"
            )
        return _Field(content)
    found = [m for m in _WORD.finditer(content) if m.group() in FIELDS]
    if len(found) != 1:
        names = ", ".join(repr(m.group()) for m in found) or "none"
        raise PatternError(
            f"pattern {pattern!r}: the optional part {{{content}}} needs exactly one field"
            f" (found {names})"
        )
    (match,) = found
    return _Field(match.group(), content[: match.start()], content[match.end() :], optional=True)


def field_text(track: Track, name: str) -> str | None:
    """A field as a file name shows it: BPM whole, the key in Open Key, two-digit numbers."""
    value = getattr(track, name)
    if value is None or value == "":
        return None
    if name == "bpm":
        return str(round(value))
    if name == "key":
        return value.open_key()
    if name == "track_number":
        return f"{value:02d}"
    return str(value).strip() or None


def safe_name(stem: str, extension: str) -> str | None:
    """``stem`` + ``extension`` made valid on every system, or ``None`` if nothing is left.

    Forbidden characters become ``_`` (``:`` becomes `` -``), runs of spaces collapse,
    leading and trailing spaces and trailing dots go, names reserved on Windows get a
    trailing ``_``, and the name is cut to 255 bytes. The extension is kept as it is.
    """
    stem = unicodedata.normalize("NFC", stem).replace(":", " -")
    stem = _SPACES.sub(" ", _FORBIDDEN.sub("_", stem)).strip(" ").rstrip(". ")
    base, dot, rest = stem.partition(".")
    if base.upper() in _RESERVED:  # Windows reserves CON and CON.anything
        stem = f"{base}_{dot}{rest}"
    budget = MAX_NAME_BYTES - len(extension.encode("utf-8"))
    encoded = stem.encode("utf-8")
    if len(encoded) > budget:
        stem = encoded[:budget].decode("utf-8", errors="ignore").rstrip(". ")
    return stem + extension if stem else None
