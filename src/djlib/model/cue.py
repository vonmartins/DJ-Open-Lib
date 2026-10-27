"""Cue points and loops."""

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field

from djlib.model._validate import check_color, check_int, check_text, set_field
from djlib.model.errors import ValidationError
from djlib.model.unmapped import JSONValue, copy_unmapped


class CueKind(enum.Enum):
    HOT = "hot"
    MEMORY = "memory"
    LOOP = "loop"


@dataclass(frozen=True, slots=True, kw_only=True)
class Cue:
    """A cue or loop. Positions are integer microseconds from the start of the track.

    ``slot`` is the hot-cue pad index; a loop with a slot is a hot loop. Only loops
    have ``end_us`` (required) and ``active``.
    """

    kind: CueKind
    start_us: int
    slot: int | None = None
    name: str | None = None
    color: str | None = None
    end_us: int | None = None
    active: bool = False
    unmapped: Mapping[str, JSONValue] = field(default_factory=dict[str, JSONValue])

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CueKind):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Cue", "kind", "must be a CueKind")
        check_int("Cue", "start_us", self.start_us, minimum=0, required=True)
        check_int("Cue", "slot", self.slot, minimum=0)
        check_text("Cue", "name", self.name)
        set_field(self, "color", check_color("Cue", "color", self.color))
        if type(self.active) is not bool:
            raise ValidationError("Cue", "active", "must be a boolean")

        if self.kind is CueKind.LOOP:
            check_int("Cue", "end_us", self.end_us, required=True)
            if self.end_us is not None and self.end_us <= self.start_us:
                raise ValidationError("Cue", "end_us", "must be after start_us")
        else:
            if self.end_us is not None:
                raise ValidationError("Cue", "end_us", "only loops have an end")
            if self.active:
                raise ValidationError("Cue", "active", "only loops can be active")

        set_field(self, "unmapped", copy_unmapped(self.unmapped, entity="Cue"))
