import dataclasses

from djlib.adapters.contract import Capabilities
from djlib.model.library import Library
from djlib.model.playlist import Folder, MatchMode, Playlist, Rule, Smartlist
from djlib.model.track import Track
from djlib.planning.diff import diff_export
from djlib.planning.model import FieldChange, NodeChange

PLAYLISTS_ONLY = Capabilities(track_fields=frozenset({"title", "artist"}), folders=True)
WITH_COLLECTION = Capabilities(
    track_fields=frozenset({"title", "artist", "bpm"}), folders=True, collection=True
)

A, B, C = (Track(path_origin=f"/music/{n}.mp3", title=n.upper()) for n in "abc")


def library(*nodes: object, tracks: tuple[Track, ...] = (A, B, C)) -> Library:
    return Library.build(tracks, nodes)  # pyright: ignore[reportArgumentType]


def test_new_playlist_into_empty_target() -> None:
    desired = library(
        Folder(name="Techno", children=(Playlist(name="Peak", entries=(A.id, B.id, C.id)),))
    )

    nodes, tracks, untouched = diff_export(Library(), desired, None, PLAYLISTS_ONLY)

    assert nodes == (
        NodeChange(change="added", path=("Techno",), kind="folder"),
        NodeChange(
            change="added",
            path=("Techno", "Peak"),
            kind="playlist",
            entries_added=(A.path, B.path, C.path),
        ),
    )
    assert tracks == ()
    assert untouched == 0


def test_identical_target_has_no_changes() -> None:
    desired = library(Playlist(name="P", entries=(A.id, B.id)))
    # The target was read back with fresh ids; matching is by path.
    a2, b2 = (dataclasses.replace(t, id=Track(path_origin=t.path).id) for t in (A, B))
    current = Library.build([a2, b2], [Playlist(name="P", entries=(a2.id, b2.id))])

    assert diff_export(current, desired, None, PLAYLISTS_ONLY) == ((), (), 0)


def test_entries_added_removed_and_reordered() -> None:
    current = library(Playlist(name="P", entries=(A.id, B.id, C.id)))

    added_and_removed = diff_export(
        current, library(Playlist(name="P", entries=(C.id, B.id))), None, PLAYLISTS_ONLY
    )[0]
    reordered = diff_export(
        current, library(Playlist(name="P", entries=(C.id, B.id, A.id))), None, PLAYLISTS_ONLY
    )[0]

    assert added_and_removed == (
        NodeChange(
            change="updated",
            path=("P",),
            kind="playlist",
            entries_removed=(A.path,),
            reordered=True,
        ),
    )
    assert reordered == (
        NodeChange(change="updated", path=("P",), kind="playlist", reordered=True),
    )


def test_appended_entry_is_not_a_reorder() -> None:
    current = library(Playlist(name="P", entries=(A.id,)))

    (change,) = diff_export(
        current, library(Playlist(name="P", entries=(A.id, B.id))), None, PLAYLISTS_ONLY
    )[0]

    assert (change.entries_added, change.reordered) == ((B.path,), False)


def test_reordered_folder() -> None:
    x, y = Playlist(name="X"), Playlist(name="Y")
    current = library(Folder(name="F", children=(x, y)))

    nodes = diff_export(current, library(Folder(name="F", children=(y, x))), None, PLAYLISTS_ONLY)[
        0
    ]

    assert nodes == (NodeChange(change="updated", path=("F",), kind="folder", reordered=True),)


def test_smartlist_rules_changed() -> None:
    rule = Rule(field="genre", operator="is", values=("Techno",))
    current = library(Smartlist(name="S", match=MatchMode.ALL, rules=(rule,)))
    other = dataclasses.replace(rule, values=("House",))

    nodes = diff_export(
        current,
        library(Smartlist(name="S", match=MatchMode.ALL, rules=(other,))),
        None,
        PLAYLISTS_ONLY,
    )[0]

    assert nodes == (NodeChange(change="updated", path=("S",), kind="smartlist"),)


def test_extra_playlist_in_target_is_untouched() -> None:
    current = library(
        Playlist(name="Old"), Folder(name="Only there", children=(Playlist(name="Q"),))
    )

    nodes, _, untouched = diff_export(current, library(Playlist(name="New")), None, PLAYLISTS_ONLY)

    assert [n.path for n in nodes] == [("New",)]
    assert untouched == 2


def test_selection_limits_the_compared_nodes() -> None:
    peak = Playlist(name="Peak", entries=(A.id,))
    desired = library(
        Folder(name="Techno", children=(peak,)), Playlist(name="Warm", entries=(B.id,))
    )

    nodes = diff_export(Library(), desired, frozenset({desired.playlists[0].id}), PLAYLISTS_ONLY)[0]

    assert [n.path for n in nodes] == [("Techno",), ("Techno", "Peak")]


def test_tracks_compared_only_with_a_collection() -> None:
    current = library(tracks=(A, dataclasses.replace(B, title="Old", bpm=120.0)))

    assert diff_export(current, library(), None, PLAYLISTS_ONLY)[1] == ()
    tracks = diff_export(current, library(), None, WITH_COLLECTION)[1]
    assert [(t.change, t.path, t.fields) for t in tracks] == [
        ("updated", B.path, (FieldChange("title", "Old", "B"), FieldChange("bpm", 120.0, None))),
        ("added", C.path, (FieldChange("title", None, "C"),)),
    ]
