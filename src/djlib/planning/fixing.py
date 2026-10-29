"""Planning fixes and rules on the library's tracks."""

from dataclasses import dataclass

from djlib.adapters.losses import display_name
from djlib.planning.model import FieldChange, TrackChange
from djlib.rules.ruleset import RuleSet
from djlib.rules.runner import run
from djlib.store import Store
from djlib.store.operations import EditTrack


@dataclass(frozen=True, slots=True, kw_only=True)
class FixPlan:
    operations: tuple[EditTrack, ...]
    tracks: tuple[TrackChange, ...]
    warnings: tuple[str, ...]


def plan_fix(store: Store, ruleset: RuleSet) -> FixPlan:
    """The edits ``ruleset`` makes to every track. Changes nothing."""
    operations: list[EditTrack] = []
    changes: list[TrackChange] = []
    warnings: list[str] = []
    for track in sorted(store.list_tracks(), key=lambda t: t.path):
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
