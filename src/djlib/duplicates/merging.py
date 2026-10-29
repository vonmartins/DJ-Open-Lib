"""The values a kept track ends with after its duplicates are merged into it."""

import dataclasses
from collections.abc import Sequence
from typing import Any

from djlib.model.track import Track

# Properties of the kept file itself, never taken from another file.
_OWN = frozenset(
    {
        "id",
        "path",
        "path_origin",
        "duration_us",
        "bitrate",
        "sample_rate",
        "file_format",
        "date_modified",
        "unmapped",
    }
)
# Fields combined by their own rule below.
_COMBINED = frozenset(
    {"play_count", "rating", "date_added", "last_played", "tags", "cues", "beatgrid"}
)
FILLED = tuple(
    f.name
    for f in dataclasses.fields(Track)
    if f.init and f.name not in _OWN and f.name not in _COMBINED
)


def merge(keeper: Track, others: Sequence[Track]) -> Track:
    """``keeper`` with what ``others`` (best first) add to it; its own values are kept."""
    changes: dict[str, Any] = {}
    for name in FILLED:
        if _empty(getattr(keeper, name)):
            value = next((v for o in others if not _empty(v := getattr(o, name))), None)
            if value is not None:
                changes[name] = value
    everyone = (keeper, *others)
    if not keeper.cues and (cued := next((o for o in others if o.cues), None)):
        changes["cues"] = cued.cues
    if keeper.beatgrid is None and (grid := next((o.beatgrid for o in others if o.beatgrid), None)):
        changes["beatgrid"] = grid
    counts = [t.play_count for t in everyone if t.play_count is not None]
    if counts:
        changes["play_count"] = sum(counts)
    ratings = [t.rating for t in everyone if t.rating is not None]
    if ratings:
        changes["rating"] = max(ratings)
    added = [t.date_added for t in everyone if t.date_added is not None]
    if added:
        changes["date_added"] = min(added)
    played = [t.last_played for t in everyone if t.last_played is not None]
    if played:
        changes["last_played"] = max(played)
    tags = tuple(dict.fromkeys(tag for t in everyone for tag in t.tags))
    if tags != keeper.tags:
        changes["tags"] = tags
    merged = dataclasses.replace(keeper, **changes)
    return keeper if merged == keeper else merged


def _empty(value: object) -> bool:
    return value is None or value == ""
