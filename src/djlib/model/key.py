"""Musical keys: one canonical value per key, rendered in Open Key or musical notation.

Camelot notation is intentionally not supported (licensing).
"""

import enum
import re
from dataclasses import dataclass

from djlib.model.errors import ValidationError

# Pitch classes: C=0, C#/Db=1, ... B=11.
_SPELLING = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
_LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACCIDENTALS = {"": 0, "#": 1, "♯": 1, "b": -1, "♭": -1}
_MAJOR_SUFFIXES = {"", "maj", "major"}
_MINOR_SUFFIXES = {"m", "min", "minor"}

_MUSICAL = re.compile(r"^([A-Ga-g])([#♯b♭]?)\s*([A-Za-z]*)$")
_OPEN_KEY = re.compile(r"^0?([1-9]|1[0-2])([dDmM])$")

# Open Key 1d is C major and 1m is A minor; each step adds a fifth (7 semitones).
_OPEN_KEY_BASE = {"major": 0, "minor": 9}


class Mode(enum.Enum):
    MAJOR = "major"
    MINOR = "minor"


@dataclass(frozen=True, slots=True, kw_only=True)
class Key:
    """One of the 24 keys: a tonic pitch class (0-11, C=0) and a mode."""

    tonic: int
    mode: Mode

    def __post_init__(self) -> None:
        if type(self.tonic) is not int or not 0 <= self.tonic <= 11:
            raise ValidationError("Key", "tonic", "must be an integer from 0 to 11")
        if not isinstance(self.mode, Mode):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Key", "mode", "must be a Mode")

    @property
    def code(self) -> int:
        """Integer from 0 to 23 used for storage: tonic + 12 for minor keys."""
        return self.tonic + (12 if self.mode is Mode.MINOR else 0)

    @classmethod
    def from_code(cls, code: int) -> "Key":
        if type(code) is not int or not 0 <= code <= 23:
            raise ValidationError("Key", "code", "must be an integer from 0 to 23")
        return cls(tonic=code % 12, mode=Mode.MINOR if code >= 12 else Mode.MAJOR)

    def open_key(self) -> str:
        number = (7 * (self.tonic - _OPEN_KEY_BASE[self.mode.value])) % 12 + 1
        return f"{number}{'m' if self.mode is Mode.MINOR else 'd'}"

    def musical(self) -> str:
        return _SPELLING[self.tonic] + ("m" if self.mode is Mode.MINOR else "")


def parse_open_key(text: str) -> Key | None:
    """Parse Open Key notation such as ``1m``, ``01m`` or ``12d``; ``None`` if unknown."""
    match = _OPEN_KEY.match(text.strip())
    if match is None:
        return None
    number, suffix = int(match.group(1)), match.group(2).lower()
    mode = Mode.MINOR if suffix == "m" else Mode.MAJOR
    tonic = (_OPEN_KEY_BASE[mode.value] + 7 * (number - 1)) % 12
    return Key(tonic=tonic, mode=mode)


def parse_musical(text: str) -> Key | None:
    """Parse musical notation such as ``F#m``, ``Bb``, ``Eb minor``; ``None`` if unknown.

    A lone upper-case ``M`` suffix is ambiguous across apps and is not accepted.
    """
    match = _MUSICAL.match(text.strip())
    if match is None:
        return None
    letter, accidental, suffix = match.groups()
    if suffix == "m":
        mode = Mode.MINOR
    elif suffix.lower() in _MAJOR_SUFFIXES and suffix != "M":
        mode = Mode.MAJOR
    elif suffix.lower() in _MINOR_SUFFIXES and suffix not in {"M", "m"}:
        mode = Mode.MINOR
    else:
        return None
    tonic = (_LETTERS[letter.upper()] + _ACCIDENTALS[accidental]) % 12
    return Key(tonic=tonic, mode=mode)
