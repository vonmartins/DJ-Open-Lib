import dataclasses

import pytest

from djlib.model.errors import ValidationError
from djlib.model.ids import new_node_id, new_track_id
from djlib.model.playlist import Folder, MatchMode, Playlist, Rule, Smartlist
from djlib.model.track import Track
from djlib.store import ConflictError, NotFoundError, Store


@pytest.fixture
def track(store: Store) -> Track:
    added = Track(path_origin="/music/a.mp3")
    store.add_track(added)
    return added


def test_add_and_get_subtree(store: Store, track: Track) -> None:
    smart = Smartlist(
        name="DnB",
        match=MatchMode.ANY,
        rules=(Rule(field="genre", operator="contains", values=("Drum", 1, None, [2])),),
    )
    tree = Folder(
        name="Gigs",
        children=(
            Folder(name="2026", children=(Playlist(name="Warmup", entries=(track.id,)),)),
            smart,
        ),
        unmapped={"traktor": {"UUID": "x"}},
    )

    store.add_node(tree)

    assert store.get_node(tree.id) == tree
    assert store.get_node(smart.id) == smart
    assert store.children() == (tree,)
    assert store.children(tree.id) == tree.children


def test_add_at_index_shifts_siblings(store: Store) -> None:
    a, b, c = Playlist(name="a"), Playlist(name="b"), Playlist(name="c")
    store.add_node(a)
    store.add_node(c)

    store.add_node(b, index=1)
    store.add_node(Playlist(name="first"), index=0)

    assert [n.name for n in store.children()] == ["first", "a", "b", "c"]


def test_add_under_folder_appends(store: Store) -> None:
    folder = Folder(name="f", children=(Playlist(name="one"),))
    store.add_node(folder)

    store.add_node(Playlist(name="two"), parent_id=folder.id)

    assert [n.name for n in store.children(folder.id)] == ["one", "two"]


def test_add_under_playlist_rejected(store: Store) -> None:
    playlist = Playlist(name="p")
    store.add_node(playlist)

    with pytest.raises(ValidationError):
        store.add_node(Playlist(name="child"), parent_id=playlist.id)
    assert store.children() == (playlist,)


def test_add_under_unknown_parent(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.add_node(Playlist(name="p"), parent_id=new_node_id())


def test_entry_for_unknown_track_rejected(store: Store, track: Track) -> None:
    playlist = Playlist(name="p", entries=(track.id,))
    store.add_node(playlist)

    with pytest.raises(ValidationError):
        store.update_node(dataclasses.replace(playlist, entries=(track.id, new_track_id())))
    assert store.get_node(playlist.id) == playlist

    with pytest.raises(ValidationError):
        store.add_node(Folder(name="f", children=(Playlist(name="x", entries=(new_track_id(),)),)))
    assert store.children() == (playlist,)


def test_update_keeps_place_in_tree(store: Store, track: Track) -> None:
    first, second = Playlist(name="first"), Playlist(name="second")
    store.add_node(first)
    store.add_node(second)

    renamed = dataclasses.replace(first, name="renamed", entries=(track.id, track.id))
    store.update_node(renamed)

    assert store.children() == (renamed, second)


def test_update_folder_replaces_subtree(store: Store) -> None:
    folder = Folder(name="f", children=(Playlist(name="old"),))
    store.add_node(folder)
    replaced = dataclasses.replace(folder, children=(Smartlist(name="new"),))

    store.update_node(replaced)

    assert store.get_node(folder.id) == replaced


def test_update_unknown_node(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.update_node(Playlist(name="ghost"))


def test_delete_folder_recursively(store: Store, track: Track) -> None:
    inner = Folder(name="inner", children=(Playlist(name="deep", entries=(track.id,)),))
    folder = Folder(name="outer", children=(Playlist(name="p", entries=(track.id,)), inner))
    keep = Playlist(name="keep")
    store.add_node(folder)
    store.add_node(keep)

    store.delete_node(folder.id)

    assert store.children() == (keep,)
    for node in (folder, inner, *folder.children):
        with pytest.raises(NotFoundError):
            store.get_node(node.id)
    assert store.get_track(track.id) == track


def test_delete_unknown_node(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.delete_node(new_node_id())


def test_duplicate_node_id_rejected(store: Store) -> None:
    playlist = Playlist(name="p")
    store.add_node(playlist)

    with pytest.raises(ConflictError):
        store.add_node(dataclasses.replace(playlist, name="again"))


def test_children_of_playlist_rejected(store: Store) -> None:
    playlist = Playlist(name="p")
    store.add_node(playlist)

    with pytest.raises(ValidationError):
        store.children(playlist.id)


def test_negative_index_rejected(store: Store) -> None:
    store.add_node(Playlist(name="a"))
    with pytest.raises(ValidationError):
        store.add_node(Playlist(name="b"), index=-1)
