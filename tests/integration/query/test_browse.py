import datetime
import uuid
from pathlib import Path

import pytest

from tunedex.model.cue import Cue, CueKind
from tunedex.model.library import Library
from tunedex.model.playlist import Folder, MatchMode, Playlist, Rule, Smartlist
from tunedex.model.track import Track
from tunedex.planning import UnknownPlaylistError
from tunedex.query import parse_where, playlist_tree, select, status, track_view
from tunedex.snapshots import SnapshotStore
from tunedex.store import NotFoundError, Store
from tunedex.store.operations import RecordSourceValues, RegisterSource

NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)


@pytest.fixture
def tracks(tmp_path: Path) -> dict[str, Track]:
    def make(name: str, **fields: object) -> Track:
        path = tmp_path / "music" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return Track(path_origin=str(path), **fields)  # pyright: ignore[reportArgumentType]

    return {
        "a": make("techno/a.mp3", artist="beta", title="Rise", genre="Techno", bpm=132.0),
        "b": make("techno/b.mp3", artist="Alpha", title="Fall", genre="Techno", bpm=128.0),
        "c": make("house/c.mp3", artist="Alpha", title="Glow", genre="House", bpm=124.0),
    }


@pytest.fixture
def library(store: Store, tracks: dict[str, Track]) -> Store:
    a, b, c = tracks["a"], tracks["b"], tracks["c"]
    sets = Folder(
        name="Sets",
        children=(
            Playlist(name="Friday", entries=(a.id, b.id)),
            Playlist(name="Saturday", entries=(b.id, c.id)),
        ),
    )
    fast = Smartlist(
        name="Fast", match=MatchMode.ALL, rules=(Rule(field="bpm", operator="gte", values=(130,)),)
    )
    store.replace_library(Library.build(tracks.values(), (sets, fast)))
    return store


def titles(found: list[Track]) -> list[str | None]:
    return [t.title for t in found]


def test_ordered_by_artist_then_title(library: Store) -> None:
    assert titles(select(library)) == ["Fall", "Glow", "Rise"]


def test_combined_filters(library: Store, tmp_path: Path) -> None:
    found = select(
        library, where=[parse_where("genre=techno")], under=tmp_path / "music" / "techno"
    )
    assert titles(found) == ["Fall", "Rise"]
    assert titles(select(library, where=[parse_where("genre=techno"), parse_where("bpm>130")])) == [
        "Rise"
    ]


def test_playlist_folder_and_smartlist(library: Store) -> None:
    assert titles(select(library, playlists=["Sets"])) == ["Fall", "Glow", "Rise"]
    assert titles(select(library, playlists=["Sets/Friday"])) == ["Fall", "Rise"]
    assert titles(select(library, playlists=["Fast"])) == ["Rise"]


def test_unknown_playlist(library: Store) -> None:
    with pytest.raises(UnknownPlaylistError, match="Sets/Fryday"):
        select(library, playlists=["Sets/Fryday"])


def test_missing(library: Store, tracks: dict[str, Track]) -> None:
    Path(tracks["c"].path_origin).unlink()

    assert titles(select(library, missing=True)) == ["Glow"]


def test_track_view_by_path_and_id(library: Store, tracks: dict[str, Track]) -> None:
    cued = Track(
        path_origin=tracks["b"].path_origin,
        id=tracks["b"].id,
        title="Fall",
        cues=(Cue(kind=CueKind.HOT, start_us=0, slot=0), Cue(kind=CueKind.HOT, start_us=1, slot=1)),
    )
    library.update_track(cued)
    library.apply_operations(
        [RegisterSource("beets", NOW), RecordSourceValues(cued.id, "beets", {"title": "Fall"})]
    )

    view = track_view(library, cued.path_origin)

    assert view.track.title == "Fall"
    assert len(view.track.cues) == 2
    assert view.playlists == ("Sets/Friday", "Sets/Saturday")
    assert view.sources == ("beets",)
    assert view.present
    assert track_view(library, str(cued.id)).track.id == cued.id


def test_unknown_track(library: Store) -> None:
    with pytest.raises(NotFoundError, match=r"/music/none\.mp3"):
        track_view(library, "/music/none.mp3")
    with pytest.raises(NotFoundError):
        track_view(library, str(uuid.uuid4()))


def test_status(library: Store, tracks: dict[str, Track], tmp_path: Path) -> None:
    Path(tracks["a"].path_origin).unlink()
    snapshots = SnapshotStore(tmp_path / "snapshots")
    database = tmp_path / "library.db"
    snapshots.create("library", [database], reason="first")
    newest = snapshots.create("library", [database], reason="second")

    summary = status(library, snapshots)

    assert (summary.tracks, summary.missing) == (3, 1)
    assert (summary.playlists, summary.smartlists, summary.folders) == (2, 1, 1)
    assert [s.id for s in summary.snapshots] == [newest.id]
    assert summary.duplicate_groups == 0


def test_status_of_an_empty_library(tmp_path: Path) -> None:
    with Store.open(":memory:") as store:
        summary = status(store, SnapshotStore(tmp_path / "none"))

    assert (summary.tracks, summary.sources, summary.snapshots) == (0, (), ())
    assert not (tmp_path / "none").exists()


def test_playlist_tree(library: Store) -> None:
    tree = [(n.depth, n.name, n.kind, n.tracks) for n in playlist_tree(library)]

    assert tree == [
        (0, "Sets", "folder", None),
        (1, "Friday", "playlist", 2),
        (1, "Saturday", "playlist", 2),
        (0, "Fast", "smartlist", 1),
    ]
