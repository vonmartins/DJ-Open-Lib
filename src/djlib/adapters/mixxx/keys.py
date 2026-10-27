"""Mixxx's key identifiers (its ``ChromaticKey`` enum) as canonical keys."""

from djlib.model.key import Key, Mode


def key_from_id(key_id: int | None) -> Key | None:
    """1 = C major … 12 = B major, 13 = C minor … 24 = B minor; anything else is no key."""
    if key_id is None or not 1 <= key_id <= 24:
        return None
    mode = Mode.MAJOR if key_id <= 12 else Mode.MINOR
    return Key(tonic=(key_id - 1) % 12, mode=mode)
