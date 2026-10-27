"""Showing plans to people (bounded text) and to programs (complete, versioned JSON)."""

import dataclasses
import datetime
import enum
import hashlib
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePath
from typing import TypeVar, cast

from djlib.adapters.contract import FileChange, Loss
from djlib.model.beatgrid import BeatGrid
from djlib.model.key import Key
from djlib.model.unmapped import JSONValue
from djlib.planning.model import ApplyResult, FieldConflict, NodeChange, Plan, TrackChange
from djlib.planning.tree import show_path

_T = TypeVar("_T")

JSON_FORMAT = "djlib-plan"
JSON_VERSION = 1

_SYMBOLS = {"added": "+", "updated": "~", "moved": ">", "missing": "!", "present": "^"}
_TRACK_ORDER = ("added", "updated", "moved", "missing", "present")


# Text


def render_text(plan: Plan, *, limit: int = 20) -> str:
    """The plan for a terminal, listing at most ``limit`` items per section."""
    lines = [plan.title]
    if plan.empty:
        lines.append("Nothing to do.")
        lines.extend(_warnings(plan, limit))
        return "\n".join(lines) + "\n"
    if plan.tracks or plan.refreshed:
        lines.append(_track_summary(plan))
        lines.extend(_bounded(plan.tracks, limit, _track_lines, "tracks"))
    if plan.nodes or plan.untouched_nodes:
        lines.append(_node_summary(plan))
        lines.extend(_bounded(plan.nodes, limit, _node_lines, "playlists"))
    if plan.files:
        actions = Counter(f.action for f in plan.files)
        lines.append("Files: " + ", ".join(f"{n} to {a}" for a, n in sorted(actions.items())))
        lines.extend(_bounded(plan.files, limit, _file_lines, "files"))
    if plan.conflicts:
        lines.append(f"Conflicts, library value kept: {len(plan.conflicts)}")
        lines.extend(
            _bounded(
                plan.conflicts,
                limit,
                lambda c: [
                    f"  {c.label}: {c.field} is {text_value(c.field, c.library_value)} in"
                    f" the library, {text_value(c.field, c.file_value)} in the file"
                ],
                "conflicts",
            )
        )
    if plan.losses:
        lines.append(f"Losses: {len(plan.losses)}")
        for loss in plan.losses:
            examples = f" (e.g. {', '.join(loss.examples)})" if loss.examples else ""
            lines.append(f"  - {loss.description}: {loss.count}{examples}")
    lines.extend(_warnings(plan, limit))
    return "\n".join(lines) + "\n"


def _track_summary(plan: Plan) -> str:
    counts = Counter(t.change for t in plan.tracks)
    parts = [f"{counts[k]} {k}" for k in _TRACK_ORDER if counts[k]]
    if plan.refreshed:
        parts.append(f"{plan.refreshed} file states refreshed")
    return "Tracks: " + ", ".join(parts)


def _node_summary(plan: Plan) -> str:
    counts = Counter(n.change for n in plan.nodes)
    parts = [f"{counts[k]} {k}" for k in ("added", "updated") if counts[k]]
    if plan.untouched_nodes:
        parts.append(f"{plan.untouched_nodes} in the target but not in the library, left untouched")
    return "Playlists: " + ", ".join(parts)


def _track_lines(change: TrackChange) -> list[str]:
    symbol = _SYMBOLS[change.change]
    if change.change == "moved":
        lines = [f"  {symbol} {change.label}  {change.old_path} → {change.path}"]
    else:
        lines = [f"  {symbol} {change.label}  {change.path}"]
    lines.extend(
        f"      {f.field}: {text_value(f.field, f.before)} → {text_value(f.field, f.after)}"
        for f in change.fields
    )
    return lines


def _node_lines(change: NodeChange) -> list[str]:
    path = show_path(change.path)
    if change.change == "added":
        size = f", {len(change.entries_added)} entries" if change.kind == "playlist" else ""
        return [f"  + {path} ({change.kind}{size})"]
    details: list[str] = []
    if change.entries_added:
        details.append(f"{len(change.entries_added)} entries added")
    if change.entries_removed:
        details.append(f"{len(change.entries_removed)} removed")
    if change.reordered:
        details.append("reordered")
    if change.renamed_from is not None:
        details.append(f"renamed from {show_path(change.renamed_from)}")
    return [f"  ~ {path} ({change.kind}): {', '.join(details) or 'changed'}"]


def _file_lines(change: FileChange) -> list[str]:
    return [f"  {change.action} {change.path}"]


def _warnings(plan: Plan, limit: int) -> list[str]:
    if not plan.warnings:
        return []
    return [
        f"Warnings: {len(plan.warnings)}",
        *_bounded(plan.warnings, limit, lambda w: [f"  {w}"], "warnings"),
    ]


def _bounded(
    items: Sequence[_T], limit: int, lines: Callable[[_T], list[str]], noun: str
) -> list[str]:
    shown = [line for item in items[:limit] for line in lines(item)]
    if len(items) > limit:
        shown.append(f"  … and {len(items) - limit} more {noun}")
    return shown


def text_value(name: str, value: object) -> str:
    """A field value as people read it."""
    if value is None:
        return "—"
    if isinstance(value, Key):
        return f"{value.open_key()} ({value.musical()})"
    if isinstance(value, float):
        return f"{value:g}"
    if name.endswith("_us") and isinstance(value, int):
        seconds = round(value / 1_000_000)
        return f"{seconds // 60}:{seconds % 60:02d}"
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, BeatGrid):
        return f"{len(value.markers)} markers"
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        if name == "tags":
            return ", ".join(map(str, items)) or "—"
        return f"{len(items)} {name}"
    if isinstance(value, str):
        return repr(value)
    return str(value)


# JSON


def to_json(plan: Plan, result: ApplyResult | None = None) -> dict[str, JSONValue]:
    """The complete plan as a JSON-compatible document."""
    return {
        "format": JSON_FORMAT,
        "version": JSON_VERSION,
        "target": plan.target,
        "title": plan.title,
        "location": None if plan.location is None else str(plan.location),
        "empty": plan.empty,
        "tracks": [_track_json(t) for t in plan.tracks],
        "refreshed": plan.refreshed,
        "playlists": [_node_json(n) for n in plan.nodes],
        "untouched_playlists": plan.untouched_nodes,
        "files": [_file_json(f) for f in plan.files],
        "losses": [_loss_json(loss) for loss in plan.losses],
        "warnings": list(plan.warnings),
        "conflicts": [_conflict_json(c) for c in plan.conflicts],
        "result": None if result is None else _result_json(result),
    }


def _track_json(change: TrackChange) -> dict[str, JSONValue]:
    return {
        "change": change.change,
        "track_id": None if change.track_id is None else str(change.track_id),
        "path": change.path,
        "old_path": change.old_path,
        "label": change.label,
        "fields": [
            {"field": f.field, "before": json_value(f.before), "after": json_value(f.after)}
            for f in change.fields
        ],
    }


def _node_json(change: NodeChange) -> dict[str, JSONValue]:
    return {
        "change": change.change,
        "path": list(change.path),
        "kind": change.kind,
        "entries_added": list(change.entries_added),
        "entries_removed": list(change.entries_removed),
        "reordered": change.reordered,
        "renamed_from": None if change.renamed_from is None else list(change.renamed_from),
    }


def _file_json(change: FileChange) -> dict[str, JSONValue]:
    return {
        "path": str(change.path),
        "action": change.action,
        "bytes": len(change.content),
        "sha256_before": change.base_sha256,
        "sha256_after": _sha256(change.content),
        "description": change.description,
    }


def _loss_json(loss: Loss) -> dict[str, JSONValue]:
    return {
        "kind": loss.kind,
        "description": loss.description,
        "count": loss.count,
        "examples": list(loss.examples),
    }


def _conflict_json(conflict: FieldConflict) -> dict[str, JSONValue]:
    return {
        "track_id": str(conflict.track_id),
        "path": conflict.path,
        "label": conflict.label,
        "field": conflict.field,
        "library_value": json_value(conflict.library_value),
        "file_value": json_value(conflict.file_value),
    }


def _result_json(result: ApplyResult) -> dict[str, JSONValue]:
    return {
        "status": result.status,
        "snapshot": result.snapshot,
        "files_written": result.files_written,
        "operations_applied": result.operations_applied,
        "warnings": list(result.warnings),
    }


def json_value(value: object) -> JSONValue:
    """A model value as JSON: keys in both notations, dates as ISO text, times in µs."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Key):
        return {"open_key": value.open_key(), "musical": value.musical()}
    if isinstance(value, datetime.date):  # datetimes included
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return json_value(value.value)
    if isinstance(value, uuid.UUID | PurePath):
        return str(value)
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {str(k): json_value(v) for k, v in mapping.items()}
    if isinstance(value, tuple | list):
        return [json_value(item) for item in cast("Sequence[object]", value)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: json_value(getattr(value, f.name)) for f in dataclasses.fields(value)}
    raise TypeError(f"cannot convert {type(value).__name__} to JSON")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
