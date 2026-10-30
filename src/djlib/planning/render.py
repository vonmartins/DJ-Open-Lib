"""Showing plans to people (bounded text) and to programs (complete, versioned JSON)."""

import datetime
import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from typing import TypeVar, cast

from djlib.adapters.contract import FileChange, Loss
from djlib.model.beatgrid import BeatGrid
from djlib.model.encoding import to_json as json_value
from djlib.model.key import Key
from djlib.model.unmapped import JSONValue
from djlib.planning.model import (
    ApplyResult,
    ExportAction,
    FieldConflict,
    NodeChange,
    Plan,
    TrackChange,
    TrashFile,
)
from djlib.planning.tree import show_path

_T = TypeVar("_T")

JSON_FORMAT = "djlib-plan"
JSON_VERSION = 3

_SYMBOLS = {
    "added": "+",
    "updated": "~",
    "moved": ">",
    "missing": "!",
    "present": "^",
    "merged": "=",
}
_TRACK_ORDER = ("added", "updated", "moved", "missing", "present", "merged")


# Text


# A piece of text and its kind (such as "added", "heading" or "warning"), which a
# terminal may show in color. Kinds name meanings, never colors. A line is one or more.
Span = tuple[str, str | None]
Line = tuple[Span, ...]


def _line(text: str, kind: str | None = None) -> Line:
    return ((text, kind),)


def render_text(plan: Plan, *, limit: int = 20) -> str:
    """The plan for a terminal, listing at most ``limit`` items per section."""
    return "".join(
        "".join(text for text, _ in line) + "\n" for line in plan_lines(plan, limit=limit)
    )


def plan_lines(plan: Plan, *, limit: int = 20) -> list[Line]:
    """The lines of :func:`render_text`, each made of pieces of a kind."""
    lines: list[Line] = [_line(plan.title, "heading")]
    if plan.empty:
        lines.append(_line("Nothing to do."))
        lines.extend(_warnings(plan, limit))
        return lines
    if plan.tracks or plan.refreshed or plan.rebased:
        lines.append(_line(_track_summary(plan), "heading"))
        lines.extend(_bounded(plan.tracks, limit, _track_lines, "tracks"))
    if plan.nodes or plan.untouched_nodes:
        lines.append(_line(_node_summary(plan), "heading"))
        lines.extend(_bounded(plan.nodes, limit, _node_lines, "playlists"))
    if plan.files:
        actions = Counter(f.action for f in plan.files)
        summary = "Files: " + ", ".join(f"{n} to {a}" for a, n in sorted(actions.items()))
        lines.append(_line(summary, "heading"))
        lines.extend(_bounded(plan.files, limit, _file_lines, "files"))
    if plan.trash:
        total = sum(f.size for f in plan.trash)
        lines.append(
            _line(f"Files to move to the trash: {len(plan.trash)} ({file_size(total)})", "heading")
        )
        lines.extend(
            _bounded(
                plan.trash,
                limit,
                lambda f: [_line(f"  - {f.path}  ({file_size(f.size)})", "trash")],
                "files",
            )
        )
    if plan.conflicts:
        export = isinstance(plan.action, ExportAction)
        kept, other = ("target", "the target") if export else ("library", "the file")
        lines.append(_line(f"Conflicts, {kept} value kept: {len(plan.conflicts)}", "heading"))
        lines.extend(
            _bounded(
                plan.conflicts,
                limit,
                lambda c: [
                    _line(
                        f"  {c.name}: {c.field} is {text_value(c.field, c.library_value)} in"
                        f" the library, {text_value(c.field, c.file_value)} in {other}",
                        "warning",
                    )
                ],
                "conflicts",
            )
        )
    if plan.losses:
        lines.append(_line(f"Losses: {len(plan.losses)}", "heading"))
        for loss in plan.losses:
            examples = f" (e.g. {', '.join(loss.examples)})" if loss.examples else ""
            lines.append(_line(f"  - {loss.description}: {loss.count}{examples}", "warning"))
    lines.extend(_warnings(plan, limit))
    return lines


def _track_summary(plan: Plan) -> str:
    counts = Counter(t.change for t in plan.tracks)
    parts = [f"{counts[k]} {k}" for k in _TRACK_ORDER if counts[k]]
    if plan.refreshed:
        parts.append(f"{plan.refreshed} file states refreshed")
    if plan.rebased:
        parts.append(f"merge base updated for {plan.rebased}")
    return "Tracks: " + ", ".join(parts)


def _node_summary(plan: Plan) -> str:
    counts = Counter(n.change for n in plan.nodes)
    parts = [f"{counts[k]} {k}" for k in ("added", "updated", "removed") if counts[k]]
    if plan.untouched_nodes:
        parts.append(f"{plan.untouched_nodes} in the target but not in the library, left untouched")
    return "Playlists: " + ", ".join(parts)


def _track_lines(change: TrackChange) -> list[Line]:
    symbol, kind = _SYMBOLS[change.change], change.change
    lines: list[Line]
    if change.change == "moved":
        lines = [_line(f"  {symbol} {change.name}  {change.old_path} → {change.path}", kind)]
    elif change.change == "merged":
        merged = f"  {symbol} {change.name}  {change.path} → merged into {change.merged_into}"
        return [_line(merged, kind)]
    else:
        lines = [_line(f"  {symbol} {change.name}  {change.path}", kind)]
    if change.change == "added":
        return lines  # one line each; the JSON rendering lists their fields
    lines.extend(
        (
            (f"      {f.field}: ", None),
            (text_value(f.field, f.before), "before"),
            (" → ", "notice"),
            (text_value(f.field, f.after), "after"),
            *(((f"  ({f.by})", "notice"),) if f.by else ()),
        )
        for f in change.fields
    )
    return lines


def _node_lines(change: NodeChange) -> list[Line]:
    path = show_path(change.path)
    if change.change == "removed":
        return [_line(f"  - {path} ({change.kind})", "removed")]
    if change.change == "added":
        size = f", {len(change.entries_added)} entries" if change.kind == "playlist" else ""
        return [_line(f"  + {path} ({change.kind}{size})", "added")]
    details: list[str] = []
    if change.entries_added:
        details.append(f"{len(change.entries_added)} entries added")
    if change.entries_removed:
        details.append(f"{len(change.entries_removed)} removed")
    if change.reordered:
        details.append("reordered")
    if change.renamed_from is not None:
        details.append(f"renamed from {show_path(change.renamed_from)}")
    return [_line(f"  ~ {path} ({change.kind}): {', '.join(details) or 'changed'}", "updated")]


def _file_lines(change: FileChange) -> list[Line]:
    return [_line(f"  {change.action} {change.path}", "updated")]


def _warnings(plan: Plan, limit: int) -> list[Line]:
    if not plan.warnings:
        return []
    return [
        _line(f"Warnings: {len(plan.warnings)}", "heading"),
        *_bounded(plan.warnings, limit, lambda w: [_line(f"  {w}", "warning")], "warnings"),
    ]


def _bounded(
    items: Sequence[_T], limit: int, lines: Callable[[_T], list[Line]], noun: str
) -> list[Line]:
    shown = [line for item in items[:limit] for line in lines(item)]
    if len(items) > limit:
        shown.append(_line(f"  … and {len(items) - limit} more {noun}", "notice"))
    return shown


def file_size(size: int) -> str:
    """A size in bytes as people read it."""
    if size < 1_000_000:
        return f"{size / 1000:.0f} kB"
    if size < 1_000_000_000:
        return f"{size / 1_000_000:.1f} MB"
    return f"{size / 1_000_000_000:.2f} GB"


def bpm_text(bpm: float) -> str:
    """A tempo with at most two decimals and no trailing zeros: 128, 127.5, 174.25."""
    return f"{round(bpm, 2):g}"


def text_value(name: str, value: object) -> str:
    """A field value as people read it."""
    if value is None:
        return "—"
    if name == "bpm" and isinstance(value, float):
        return bpm_text(value)
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
        "rebased": plan.rebased,
        "playlists": [_node_json(n) for n in plan.nodes],
        "untouched_playlists": plan.untouched_nodes,
        "files": [_file_json(f) for f in plan.files],
        "trash": [_trash_json(f) for f in plan.trash],
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
        "merged_into": change.merged_into,
        "name": change.name,
        "fields": [
            {
                "field": f.field,
                "before": json_value(f.before),
                "after": json_value(f.after),
                "by": f.by,
            }
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


def _trash_json(file: TrashFile) -> dict[str, JSONValue]:
    return {"path": file.path, "bytes": file.size}


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
        "name": conflict.name,
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
        "files_trashed": result.files_trashed,
        "warnings": list(result.warnings),
    }


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
