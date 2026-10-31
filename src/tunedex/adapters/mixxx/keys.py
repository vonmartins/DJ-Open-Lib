"""Mixxx's key identifiers (its ``ChromaticKey`` enum) and ``KeyMap`` messages."""

from tunedex.adapters.mixxx.beats import SOURCE_USER, encode_field
from tunedex.model.key import Key, Mode

KEY_MAP = "KeyMap-1.0"


def key_from_id(key_id: int | None) -> Key | None:
    """1 = C major … 12 = B major, 13 = C minor … 24 = B minor; anything else is no key."""
    if key_id is None or not 1 <= key_id <= 24:
        return None
    mode = Mode.MAJOR if key_id <= 12 else Mode.MINOR
    return Key(tonic=(key_id - 1) % 12, mode=mode)


def key_to_id(key: Key) -> int:
    return key.tonic + 1 + (12 if key.mode is Mode.MINOR else 0)


def encode_key_map(key_id: int, text: str, source: int = SOURCE_USER) -> bytes:
    """``KeyMap { global_key = 1; global_key_text = 2; source = 4 }``"""
    return encode_field(1, key_id) + encode_field(2, text.encode()) + encode_field(4, source)
