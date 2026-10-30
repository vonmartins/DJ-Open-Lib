"""Working out which data a target format cannot represent."""

import posixpath
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from tunedex.adapters.contract import MAX_LOSS_EXAMPLES, Capabilities, Loss
from tunedex.model.cue import CueKind
from tunedex.model.ids import TrackId
from tunedex.model.library import Library
from tunedex.model.playlist import Folder, Node, Smartlist
from tunedex.model.track import DATE_FIELDS, INT_FIELDS, TEXT_FIELDS, Track

# Every optional Track field, in a stable order for reporting.
TRACK_FIELDS: tuple[str, ...] = (
    *TEXT_FIELDS,
    *INT_FIELDS,
    *DATE_FIELDS,
    "bpm",
    "key",
    "color",
    "last_played",
)


def display_name(track: Track) -> str:
    if track.artist and track.title:
        return f"{track.artist} - {track.title}"
    return track.title or posixpath.basename(track.path)


@dataclass
class LossCollector:
    """Accumulates affected items per loss kind, keeping the first examples."""

    _order: list[str] = field(default_factory=list[str])
    _descriptions: dict[str, str] = field(default_factory=dict[str, str])
    _counts: dict[str, int] = field(default_factory=dict[str, int])
    _examples: dict[str, list[str]] = field(default_factory=dict[str, list[str]])

    def add(self, kind: str, description: str, example: str) -> None:
        if kind not in self._counts:
            self._order.append(kind)
            self._descriptions[kind] = description
            self._counts[kind] = 0
            self._examples[kind] = []
        self._counts[kind] += 1
        if len(self._examples[kind]) < MAX_LOSS_EXAMPLES:
            self._examples[kind].append(example)

    def losses(self) -> tuple[Loss, ...]:
        return tuple(
            Loss(
                kind=kind,
                description=self._descriptions[kind],
                count=self._counts[kind],
                examples=tuple(self._examples[kind]),
            )
            for kind in self._order
        )


def compute_losses(
    library: Library,
    written_tracks: Sequence[TrackId],
    written_nodes: Iterable[Node],
    capabilities: Capabilities,
    adapter_name: str,
    collector: LossCollector | None = None,
) -> LossCollector:
    """Record the generic losses of writing ``written_tracks`` and ``written_nodes``.

    Adapters add their own format-specific losses to the returned collector.
    """
    losses = collector or LossCollector()
    unique_ids = list(dict.fromkeys(written_tracks))
    tracks = sorted((library.tracks[i] for i in unique_ids), key=lambda t: t.path)

    for name in TRACK_FIELDS:
        if name in capabilities.track_fields:
            continue
        for track in tracks:
            if getattr(track, name) is not None:
                losses.add(f"field:{name}", f"{name} is not stored", display_name(track))

    for kind in CueKind:
        if kind in capabilities.cue_kinds:
            continue
        for track in tracks:
            if any(cue.kind is kind for cue in track.cues):
                losses.add(
                    f"cue:{kind.value}", f"{kind.value} cues are not stored", display_name(track)
                )

    for track in tracks:
        if track.beatgrid is not None and not capabilities.beatgrid:
            losses.add("beatgrid", "beatgrids are not stored", display_name(track))
        if track.tags and not capabilities.tags:
            losses.add("tags", "tags are not stored", display_name(track))
        formats = set(track.unmapped).union(*(cue.unmapped for cue in track.cues))
        for name in sorted(formats - {adapter_name}):
            losses.add(
                f"unmapped:{name}", f"data kept from {name} is not stored", display_name(track)
            )

    for node in written_nodes:
        if isinstance(node, Smartlist) and not capabilities.smartlists:
            losses.add("smartlists", "smartlists are not written", node.name)
        if isinstance(node, Folder) and not capabilities.folders:
            losses.add("folders", "folders are not written", node.name)
        for name in sorted(set(node.unmapped) - {adapter_name}):
            losses.add(f"unmapped:{name}", f"data kept from {name} is not stored", node.name)

    if not capabilities.collection:
        written = set(unique_ids)
        outside = sorted(
            (t for i, t in library.tracks.items() if i not in written), key=lambda t: t.path
        )
        for track in outside:
            losses.add(
                "tracks-outside-playlists",
                "tracks in no written playlist are not written",
                display_name(track),
            )
    return losses
