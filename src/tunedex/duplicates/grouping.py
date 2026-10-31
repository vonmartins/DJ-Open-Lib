"""Gathering tracks that are the same song into groups."""

from collections import defaultdict
from collections.abc import Iterable, Sequence

from tunedex.duplicates.normalize import name_key
from tunedex.model.ids import TrackId
from tunedex.model.track import Track

MAX_LENGTH_GAP_US = 3_000_000


def recording_id(track: Track) -> str | None:
    """The MusicBrainz recording id the track carries, from enrichment or beets."""
    for source, key in (("musicbrainz", "recording_id"), ("beets", "mb_trackid")):
        data = track.unmapped.get(source)
        if isinstance(data, dict):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return None


class _Sets:
    def __init__(self) -> None:
        self._parent: dict[TrackId, TrackId] = {}

    def find(self, item: TrackId) -> TrackId:
        parent = self._parent.setdefault(item, item)
        if parent != item:
            parent = self._parent[item] = self.find(parent)
        return parent

    def join(self, first: TrackId, second: TrackId) -> None:
        a, b = self.find(first), self.find(second)
        if a != b:
            self._parent[max(a, b)] = min(a, b)


def find_groups(tracks: Iterable[Track]) -> list[list[Track]]:
    """Groups of two or more tracks, each track in at most one, in no particular order."""
    by_id = {t.id: t for t in tracks}
    sets = _Sets()
    by_recording: defaultdict[str, list[Track]] = defaultdict(list)
    by_name: defaultdict[tuple[str, str], list[Track]] = defaultdict(list)
    for track in by_id.values():
        if (recording := recording_id(track)) is not None:
            by_recording[recording].append(track)
        if (key := name_key(track)) is not None:
            by_name[key].append(track)
    for same in by_recording.values():
        for track in same[1:]:
            sets.join(same[0].id, track.id)
    for same in by_name.values():
        for cluster in _length_clusters(same):
            for track in cluster[1:]:
                sets.join(cluster[0].id, track.id)
    groups: defaultdict[TrackId, list[Track]] = defaultdict(list)
    for track in by_id.values():
        groups[sets.find(track.id)].append(track)
    return [group for group in groups.values() if len(group) > 1]


def _length_clusters(tracks: Sequence[Track]) -> list[list[Track]]:
    """Tracks of one name split where lengths differ by more than 3 seconds.

    Tracks of unknown length join the first cluster: an unknown length keeps nothing apart.
    """
    known = sorted((t for t in tracks if t.duration_us), key=lambda t: (t.duration_us, t.path))
    unknown = sorted((t for t in tracks if not t.duration_us), key=lambda t: t.path)
    clusters: list[list[Track]] = []
    for track in known:
        last = clusters[-1][-1] if clusters else None
        if last is None or (track.duration_us or 0) - (last.duration_us or 0) > MAX_LENGTH_GAP_US:
            clusters.append([track])
        else:
            clusters[-1].append(track)
    if not clusters:
        return [unknown]
    clusters[0].extend(unknown)
    return clusters
