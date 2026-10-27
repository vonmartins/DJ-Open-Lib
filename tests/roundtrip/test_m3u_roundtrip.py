"""Writing a library as M3U and reading it back keeps everything M3U can hold."""

import tempfile
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from djlib.adapters.m3u import M3UAdapter
from djlib.adapters.m3u.names import sanitize
from djlib.model.library import Library
from djlib.model.paths import normalize_path
from djlib.model.playlist import Folder, Node, Playlist
from djlib.model.track import Track
from support.adapter_contract import write_plan_to_disk

FIXTURES = Path(__file__).parents[1] / "fixtures" / "m3u"

# Values M3U can represent exactly.
safe_names = st.from_regex(r"\A[A-Za-z0-9][A-Za-z0-9 _-]{0,10}[A-Za-z0-9]\Z").filter(
    lambda n: sanitize(n) == n
)
words = st.text(st.characters(categories=("L", "N")), min_size=1, max_size=8)
titles = st.lists(words, min_size=1, max_size=3).map(" ".join)


@st.composite
def m3u_tracks(draw: st.DrawFn, index: int) -> Track:
    return Track(
        path_origin=f"/music/{draw(words)}/{index}.mp3",
        artist=draw(st.none() | titles),
        title=draw(titles),
        duration_us=draw(st.none() | st.integers(0, 3600).map(lambda s: s * 1_000_000)),
    )


@st.composite
def m3u_libraries(draw: st.DrawFn) -> Library:
    tracks = [draw(m3u_tracks(i)) for i in range(draw(st.integers(1, 6)))]
    ids = [t.id for t in tracks]

    def level(depth: int) -> list[Node]:
        names = draw(st.lists(safe_names, min_size=1, max_size=3, unique_by=str.casefold))
        nodes: list[Node] = []
        for name in names:
            if depth > 0 and draw(st.booleans()):
                nodes.append(Folder(name=name, children=tuple(level(depth - 1))))
            else:
                entries = draw(st.lists(st.sampled_from(ids), max_size=5))
                nodes.append(Playlist(name=name, entries=tuple(entries)))
        return nodes

    return Library.build(tracks, level(2))


def shape(library: Library, nodes: tuple[Node, ...]) -> list[Any]:
    """Comparable structure, ordered like the reader orders a directory."""
    result: list[Any] = []
    for node in sorted(nodes, key=lambda n: (n.name.casefold(), n.name)):
        if isinstance(node, Folder):
            result.append(("folder", node.name, shape(library, node.children)))
        elif isinstance(node, Playlist):
            entries = [library.tracks[e] for e in node.entries]
            result.append(
                (
                    "playlist",
                    node.name,
                    [(t.path, t.artist, t.title, t.duration_us) for t in entries],
                )
            )
    return result


def round_trip(library: Library, location: Path, adapter: M3UAdapter) -> Library:
    write_plan_to_disk(adapter.plan_write(library, location))
    return adapter.read(location).library


@given(library=m3u_libraries())
@settings(max_examples=60, deadline=None)
def test_generated_libraries_round_trip(library: Library) -> None:
    # A fresh directory per example: leftovers from earlier examples would be read back.
    with tempfile.TemporaryDirectory() as directory:
        read_back = round_trip(library, Path(directory) / "out", M3UAdapter())
    assert shape(read_back, read_back.playlists) == shape(library, library.playlists)


def test_fixture_tree_round_trip_absolute(tmp_path: Path) -> None:
    original = M3UAdapter().read(FIXTURES / "tree").library
    read_back = round_trip(original, tmp_path / "out", M3UAdapter())
    assert shape(read_back, read_back.playlists) == shape(original, original.playlists)


def test_relative_paths_round_trip(tmp_path: Path) -> None:
    music = normalize_path(str(tmp_path / "music"))
    tracks = [Track(path_origin=f"{music}/{n}.mp3", title=f"T{n}") for n in range(3)]
    library = Library.build(
        tracks,
        [
            Folder(
                name="Gigs", children=(Playlist(name="Set", entries=tuple(t.id for t in tracks)),)
            )
        ],
    )

    adapter = M3UAdapter(relative_paths=True)
    plan = adapter.plan_write(library, tmp_path / "lists")
    assert b"../" in plan.changes[0].content or b"..\\" in plan.changes[0].content
    read_back = round_trip(library, tmp_path / "lists", adapter)

    assert shape(read_back, read_back.playlists) == shape(library, library.playlists)
