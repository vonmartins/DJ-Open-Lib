"""The library: all tracks and the playlist tree, checked for consistency."""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field

from tunedex.model._validate import set_field
from tunedex.model.errors import ValidationError
from tunedex.model.ids import NodeId, TrackId
from tunedex.model.playlist import Folder, Node, Playlist, Smartlist
from tunedex.model.track import Track


@dataclass(frozen=True, slots=True, kw_only=True)
class Library:
    """Tracks by identifier plus the root level of the playlist tree.

    A library never contains playlist entries for unknown tracks, two tracks with
    the same normalized path, or two nodes with the same identifier.
    """

    tracks: Mapping[TrackId, Track] = field(default_factory=dict[TrackId, Track])
    playlists: tuple[Node, ...] = ()

    @classmethod
    def build(cls, tracks: Iterable[Track], playlists: Iterable[Node] = ()) -> "Library":
        return cls(tracks={t.id: t for t in tracks}, playlists=tuple(playlists))

    def __post_init__(self) -> None:
        tracks = dict(self.tracks)
        paths: dict[str, TrackId] = {}
        for track_id, track in tracks.items():
            if not isinstance(track, Track):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise ValidationError("Library", "tracks", "must contain Track values")
            if track.id != track_id:
                raise ValidationError("Library", "tracks", f"key {track_id} != track id {track.id}")
            if track.path in paths:
                raise ValidationError(
                    "Library", "tracks", f"two tracks share the normalized path {track.path!r}"
                )
            paths[track.path] = track_id
        set_field(self, "tracks", tracks)

        playlists = tuple(self.playlists)
        if any(not isinstance(n, Folder | Playlist | Smartlist) for n in playlists):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValidationError("Library", "playlists", "must contain playlist nodes")
        set_field(self, "playlists", playlists)

        node_ids: set[NodeId] = set()
        for _parent, _index, node in self.walk():
            if node.id in node_ids:
                raise ValidationError("Library", "playlists", f"node id {node.id} is used twice")
            node_ids.add(node.id)
            if isinstance(node, Playlist):
                unknown = [e for e in node.entries if e not in tracks]
                if unknown:
                    raise ValidationError(
                        "Library",
                        "playlists",
                        f"playlist {node.name!r} references unknown track {unknown[0]}",
                    )

    def walk(self) -> Iterator[tuple[NodeId | None, int, Node]]:
        """Yield ``(parent id, index under parent, node)`` for every node, parents first."""
        stack: list[tuple[NodeId | None, int, Node]] = [
            (None, i, n) for i, n in reversed(list(enumerate(self.playlists)))
        ]
        while stack:
            parent, index, node = stack.pop()
            yield parent, index, node
            if isinstance(node, Folder):
                stack.extend((node.id, i, c) for i, c in reversed(list(enumerate(node.children))))
