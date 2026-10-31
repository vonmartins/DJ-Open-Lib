"""Planning fixes and rules on the library's tracks."""

import os
from dataclasses import dataclass

from tunedex.adapters.losses import display_name
from tunedex.planning.model import FieldChange, TrackChange
from tunedex.rules.ruleset import RuleSet
from tunedex.rules.runner import run
from tunedex.store import Store
from tunedex.store.operations import EditTrack


@dataclass(frozen=True, slots=True, kw_only=True)
class FixPlan:
    operations: tuple[EditTrack, ...]
    tracks: tuple[TrackChange, ...]
    warnings: tuple[str, ...]


def plan_fix(
    store: Store, ruleset: RuleSet, under: str | os.PathLike[str] | None = None
) -> FixPlan:
    """The edits ``ruleset`` makes to every track, or those under ``under``. Changes nothing."""
    listed = store.list_tracks() if under is None else store.list_tracks_under(os.fspath(under))
    operations: list[EditTrack] = []
    changes: list[TrackChange] = []
    warnings: list[str] = []
    for track in sorted(listed, key=lambda t: t.path):
        fixed, edits, problems = run(ruleset, track)
        warnings.extend(problems)
        if not edits:
            continue
        operations.append(EditTrack(fixed))
        changes.append(
            TrackChange(
                change="updated",
                track_id=track.id,
                path=track.path,
                name=display_name(track),
                fields=tuple(FieldChange(e.field, e.before, e.after, e.by) for e in edits),
            )
        )
    return FixPlan(operations=tuple(operations), tracks=tuple(changes), warnings=tuple(warnings))
