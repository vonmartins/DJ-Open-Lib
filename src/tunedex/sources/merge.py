"""Three-way merging of field values: the last value read from a source is the base."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from tunedex.model.track import Track
from tunedex.model.unmapped import JSONValue

Encode = Callable[[str, Any], JSONValue]


@dataclass(frozen=True, slots=True)
class FieldDisagreement:
    """A field changed both in tunedex and in the source since the base; tunedex's value is kept."""

    field: str
    library_value: Any
    source_value: Any


def merge_fields(
    track: Track,
    base: Mapping[str, JSONValue] | None,
    theirs: Mapping[str, Any],
    fields: Iterable[str],
    encode: Encode,
) -> tuple[dict[str, Any], list[FieldDisagreement]]:
    """Field changes for ``track`` and the disagreements, from a three-way merge.

    ``base`` holds encoded values from the last read of the source, or is ``None`` when
    the source was never read for this track: then only empty fields are filled.
    ``theirs`` holds model values; missing names count as absent values.
    """
    changes: dict[str, Any] = {}
    disagreements: list[FieldDisagreement] = []
    for name in fields:
        source_value = theirs.get(name)
        mine = getattr(track, name)
        if base is None:
            if _is_empty(mine) and not _is_empty(source_value):
                changes[name] = source_value
            continue
        encoded_mine, encoded_theirs = encode(name, mine), encode(name, source_value)
        previous = base.get(name)
        if encoded_mine == previous:
            if encoded_theirs != encoded_mine:
                changes[name] = source_value
        elif encoded_theirs not in (previous, encoded_mine):
            disagreements.append(FieldDisagreement(name, mine, source_value))
    return changes, disagreements


def _is_empty(value: object) -> bool:
    return value is None or value == ()
