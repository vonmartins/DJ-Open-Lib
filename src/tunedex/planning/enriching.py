"""Planning metadata from MusicBrainz for tracks identified by their sound.

Enrichment is a source of its own, ``musicbrainz``, merged like imports: the first time
a track is enriched its normalized fields take MusicBrainz's values; afterwards a field
edited in tunedex wins and is reported as a conflict. Tracks are not linked to recordings
as import items are: duplicate files share a recording, and each is identified by its
sound on every run. The recording id is kept in ``unmapped["musicbrainz"]``.
"""

import dataclasses
import datetime
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tunedex.adapters.losses import display_name
from tunedex.enrich import EnrichError
from tunedex.enrich.mapping import NORMALIZED, choose_release, first_release_date, map_recording
from tunedex.enrich.match import (
    Disagreement,
    Identified,
    NotRecognized,
    Unlinked,
    Unresolved,
    identify,
)
from tunedex.enrich.service import Services
from tunedex.model.encoding import to_json
from tunedex.model.track import Track
from tunedex.model.unmapped import JSONValue
from tunedex.planning.diff import diff_tracks
from tunedex.planning.model import FieldChange, FieldConflict, TrackChange
from tunedex.planning.relocating import report
from tunedex.sources.merge import FieldDisagreement, merge_fields
from tunedex.store import Store
from tunedex.store.operations import (
    ImportOperation,
    RecordSourceValues,
    RegisterSource,
    UpdateImportedTrack,
)

SOURCE = "musicbrainz"
Steps = Callable[[int, int], None]
"""Told how many of the tracks were done, and how many there are."""


@dataclass(frozen=True, slots=True, kw_only=True)
class EnrichPlan:
    operations: tuple[ImportOperation, ...]
    tracks: tuple[TrackChange, ...]
    conflicts: tuple[FieldConflict, ...]
    warnings: tuple[str, ...]


@dataclass
class _Outcomes:
    identified: list[Track] = dataclasses.field(default_factory=list[Track])
    unresolved: list[tuple[Track, Unresolved]] = dataclasses.field(
        default_factory=list[tuple[Track, Unresolved]]
    )
    not_recognized: list[Track] = dataclasses.field(default_factory=list[Track])
    unlinked: list[Track] = dataclasses.field(default_factory=list[Track])
    disagreements: list[tuple[Track, Disagreement]] = dataclasses.field(
        default_factory=list[tuple[Track, Disagreement]]
    )
    missing: list[Track] = dataclasses.field(default_factory=list[Track])
    failed: list[str] = dataclasses.field(default_factory=list[str])


def carried_recording(track: Track) -> str | None:
    """A MusicBrainz recording id the track already carries, from beets or enrichment."""
    for source, key in ((SOURCE, "recording_id"), ("beets", "mb_trackid")):
        data = track.unmapped.get(source)
        if isinstance(data, dict):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def plan_enrich(
    store: Store,
    services: Services,
    *,
    under: Path | None = None,
    now: datetime.datetime,
    steps: Steps | None = None,
) -> EnrichPlan:
    """Plan enriching the library's tracks (or those under ``under``). Changes nothing."""
    services.check()
    listed = store.list_tracks() if under is None else store.list_tracks_under(str(under))
    tracks = sorted(listed, key=lambda t: t.path)
    bases = store.source_values(SOURCE)
    outcomes = _Outcomes()
    operations: list[ImportOperation] = []
    changes: list[TrackChange] = []
    conflicts: list[FieldConflict] = []
    for done, track in enumerate(tracks, start=1):
        if steps is not None:
            steps(done - 1, len(tracks))
        path = Path(track.path_origin)
        if not path.exists():
            outcomes.missing.append(track)
            continue
        try:
            duration, fingerprint = services.fingerprint(path)
        except EnrichError as error:
            outcomes.failed.append(str(error))
            continue
        outcome = identify(
            services.lookup(duration, fingerprint),
            duration=duration,
            title=track.title,
            carried_id=carried_recording(track),
            first_release=lambda rid: first_release_date(services.recording(rid)),
        )
        match outcome:
            case Identified(recording_id, score):
                outcomes.identified.append(track)
                result = _enrich(track, services, recording_id, score, bases.get(track.id))
                merged, values, disagreements = result
                conflicts.extend(
                    FieldConflict(
                        track_id=track.id,
                        path=track.path,
                        name=display_name(track),
                        field=d.field,
                        library_value=d.library_value,
                        file_value=d.source_value,
                    )
                    for d in disagreements
                )
                if merged != track:
                    operations.append(UpdateImportedTrack(merged, SOURCE, values))
                    fields = tuple(
                        FieldChange(f.field, f.before, f.after, SOURCE)
                        for f in diff_tracks(track, merged)
                    )
                    if fields:
                        changes.append(_change(track, fields))
                elif bases.get(track.id) != values:
                    operations.append(RecordSourceValues(track.id, SOURCE, values))
            case Unresolved():
                outcomes.unresolved.append((track, outcome))
            case Unlinked():
                outcomes.unlinked.append(track)
            case NotRecognized():
                outcomes.not_recognized.append(track)
            case Disagreement():
                outcomes.disagreements.append((track, outcome))
    if steps is not None and tracks:
        steps(len(tracks), len(tracks))
    # Outcomes are reported with changes, or before anything was ever enriched; once
    # applied, a re-run of an unchanged library is quiet.
    report_all = bool(operations) or store.source(SOURCE) is None
    if operations:
        operations.insert(0, RegisterSource(SOURCE, now))
    return EnrichPlan(
        operations=tuple(operations),
        tracks=tuple(changes),
        conflicts=tuple(conflicts),
        warnings=tuple(_warnings(outcomes) if report_all else outcomes.failed[:5]),
    )


def _enrich(
    track: Track,
    services: Services,
    recording_id: str,
    score: float,
    base: dict[str, JSONValue] | None,
) -> tuple[Track, dict[str, JSONValue], list[FieldDisagreement]]:
    recording = services.recording(recording_id)
    ref = choose_release(recording, track.album)
    release = None if ref is None else services.release(ref.id)
    mapped = map_recording(recording, release, score=score)
    fields = tuple(name for name in NORMALIZED if name in mapped.fields)
    values: dict[str, JSONValue] = {name: to_json(mapped.fields[name]) for name in fields}
    if base is None:
        # First enrichment: normalize, as the plan shows every change before applying.
        updates: dict[str, Any] = {
            name: mapped.fields[name]
            for name in fields
            if getattr(track, name) != mapped.fields[name]
        }
        disagreements: list[FieldDisagreement] = []
    else:
        updates, disagreements = merge_fields(
            track, base, mapped.fields, fields, lambda _name, value: to_json(value)
        )
    if mapped.genre and not track.genre:
        updates["genre"] = mapped.genre
    unmapped = {**track.unmapped, SOURCE: mapped.unmapped}
    if unmapped != dict(track.unmapped):
        updates["unmapped"] = unmapped
    merged = dataclasses.replace(track, **updates) if updates else track
    return merged, values, disagreements


def _change(track: Track, fields: tuple[FieldChange, ...]) -> TrackChange:
    return TrackChange(
        change="updated",
        track_id=track.id,
        path=track.path,
        name=display_name(track),
        fields=fields,
    )


def _warnings(outcomes: _Outcomes) -> list[str]:
    counts = [
        f"{len(outcomes.identified)} identified",
        f"{len(outcomes.unresolved)} unresolved",
        f"{len(outcomes.unlinked)} recognized but not in MusicBrainz",
        f"{len(outcomes.not_recognized)} not recognized",
        f"{len(outcomes.disagreements)} disagree with their MusicBrainz id",
        f"{len(outcomes.missing)} skipped (file missing)",
    ]
    warnings = [f"musicbrainz: {', '.join(counts)}"]
    for track, unresolved in outcomes.unresolved[:5]:
        options = "; ".join(
            f"{c.title} - {c.artist} ({round(c.duration or 0)} s)" for c in unresolved.candidates
        )
        warnings.append(f"unresolved {track.path}: {options}")
    for track, disagreement in outcomes.disagreements[:5]:
        warnings.append(
            f"{track.path}: carries MusicBrainz recording {disagreement.carried} but sounds like"
            f" {disagreement.found}; left unchanged"
        )
    warnings.extend(
        report(outcomes.unlinked, "tracks are recognized by AcoustID but not linked to MusicBrainz")
    )
    warnings.extend(report(outcomes.not_recognized, "tracks are not recognized by AcoustID"))
    warnings.extend(report(outcomes.missing, "tracks were skipped because their files are missing"))
    warnings.extend(outcomes.failed[:5])
    return warnings
