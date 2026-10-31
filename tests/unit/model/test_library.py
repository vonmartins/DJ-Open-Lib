import pytest

from tunedex.model.errors import ValidationError
from tunedex.model.ids import new_track_id
from tunedex.model.library import Library
from tunedex.model.playlist import Folder, Playlist, Smartlist
from tunedex.model.track import Track


def test_build_indexes_tracks_by_id() -> None:
    a, b = Track(path_origin="/m/a.mp3"), Track(path_origin="/m/b.mp3")
    library = Library.build([a, b], [Playlist(name="p", entries=(a.id, b.id))])

    assert library.tracks == {a.id: a, b.id: b}


def test_empty_library() -> None:
    assert Library() == Library.build([])


def test_dangling_entry_rejected() -> None:
    a = Track(path_origin="/m/a.mp3")
    nested = Folder(name="f", children=(Playlist(name="p", entries=(new_track_id(),)),))

    with pytest.raises(ValidationError) as excinfo:
        Library.build([a], [nested])
    assert (excinfo.value.entity, excinfo.value.field) == ("Library", "playlists")


def test_duplicate_normalized_path_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Library.build([Track(path_origin=r"C:\Music\a.mp3"), Track(path_origin="c:/Music/a.mp3")])
    assert excinfo.value.field == "tracks"


def test_duplicate_node_id_rejected() -> None:
    playlist = Playlist(name="p")
    with pytest.raises(ValidationError) as excinfo:
        Library.build([], [playlist, Folder(name="f", children=(playlist,))])
    assert excinfo.value.field == "playlists"


def test_mismatched_track_key_rejected() -> None:
    track = Track(path_origin="/m/a.mp3")
    with pytest.raises(ValidationError):
        Library(tracks={new_track_id(): track})


def test_walk_yields_parents_first_with_positions() -> None:
    p1, p2, s = Playlist(name="p1"), Playlist(name="p2"), Smartlist(name="s")
    inner = Folder(name="inner", children=(p2,))
    root = Folder(name="root", children=(p1, inner))
    library = Library.build([], [root, s])

    assert [(parent, index, node.name) for parent, index, node in library.walk()] == [
        (None, 0, "root"),
        (root.id, 0, "p1"),
        (root.id, 1, "inner"),
        (inner.id, 0, "p2"),
        (None, 1, "s"),
    ]
