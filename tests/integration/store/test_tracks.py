import dataclasses
import datetime

import pytest

from tunedex.model.beatgrid import BeatGrid, BeatMarker
from tunedex.model.cue import Cue, CueKind
from tunedex.model.ids import new_track_id
from tunedex.model.key import Key, Mode
from tunedex.model.playlist import Playlist
from tunedex.model.track import Track
from tunedex.store import ConflictError, NotFoundError, Store


def full_track(path: str = "/music/a.mp3") -> Track:
    return Track(
        path_origin=path,
        title="Title",
        bpm=127.999,
        key=Key(tonic=1, mode=Mode.MINOR),
        key_original="12A",
        rating=4,
        color="#112233",
        date_added=datetime.date(2026, 10, 26),
        last_played=datetime.datetime(2026, 10, 25, 23, 59, 58, 123456),
        tags=("Peak", "Vocals"),
        cues=(
            Cue(kind=CueKind.HOT, start_us=1_234_567, slot=0, name="Drop", color="#FF0000"),
            Cue(kind=CueKind.LOOP, start_us=0, end_us=7_500_000, active=True),
        ),
        beatgrid=BeatGrid(markers=(BeatMarker(position_us=12, bpm=128.0, beat=2),)),
        unmapped={"traktor": {"LOCK": "1"}},
    )


def test_add_and_get(store: Store) -> None:
    track = full_track()
    store.add_track(track)

    assert store.get_track(track.id) == track


def test_lookup_by_path(store: Store) -> None:
    track = Track(path_origin="/music/a.mp3")
    store.add_track(track)

    assert store.find_track_by_path("/music/a.mp3") == track
    assert store.find_track_by_path("/music/./x/../a.mp3") == track
    assert store.find_track_by_path("/music/b.mp3") is None


def test_list_tracks(store: Store) -> None:
    tracks = [Track(path_origin=f"/music/{n}.mp3") for n in "cab"]
    for track in tracks:
        store.add_track(track)

    assert sorted(store.list_tracks(), key=lambda t: t.path) == sorted(tracks, key=lambda t: t.path)


def test_update_replaces_cues(store: Store) -> None:
    track = full_track()
    store.add_track(track)
    updated = dataclasses.replace(
        track, title="New", cues=(Cue(kind=CueKind.MEMORY, start_us=99),), tags=("Dark",)
    )

    store.update_track(updated)

    assert store.get_track(track.id) == updated


def test_update_can_move_a_track(store: Store) -> None:
    track = full_track()
    store.add_track(track)

    store.update_track(dataclasses.replace(track, path_origin="/other/a.mp3"))

    assert store.find_track_by_path("/music/a.mp3") is None
    assert store.find_track_by_path("/other/a.mp3") is not None


def test_update_unknown_track(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.update_track(full_track())


def test_delete_removes_playlist_entries(store: Store) -> None:
    keep, gone = Track(path_origin="/m/keep.mp3"), Track(path_origin="/m/gone.mp3")
    store.add_track(keep)
    store.add_track(gone)
    first = Playlist(name="one", entries=(keep.id, gone.id, keep.id))
    second = Playlist(name="two", entries=(gone.id,))
    store.add_node(first)
    store.add_node(second)

    store.delete_track(gone.id)

    assert store.get_node(first.id) == dataclasses.replace(first, entries=(keep.id, keep.id))
    assert store.get_node(second.id) == dataclasses.replace(second, entries=())
    with pytest.raises(NotFoundError):
        store.get_track(gone.id)


def test_delete_unknown_track(store: Store) -> None:
    with pytest.raises(NotFoundError):
        store.delete_track(new_track_id())


def test_duplicate_path_rejected(store: Store) -> None:
    store.add_track(Track(path_origin="/music/a.mp3", title="first"))
    before = store.load_library()

    with pytest.raises(ConflictError):
        store.add_track(Track(path_origin="/music/./a.mp3", title="second"))
    assert store.load_library() == before


def test_update_into_existing_path_rejected(store: Store) -> None:
    a, b = Track(path_origin="/m/a.mp3"), Track(path_origin="/m/b.mp3")
    store.add_track(a)
    store.add_track(b)

    with pytest.raises(ConflictError):
        store.update_track(dataclasses.replace(b, path_origin="/m/a.mp3"))
    assert store.get_track(b.id) == b


def test_duplicate_id_rejected(store: Store) -> None:
    track = Track(path_origin="/m/a.mp3")
    store.add_track(track)

    with pytest.raises(ConflictError):
        store.add_track(dataclasses.replace(track, path_origin="/m/b.mp3"))


def test_orphan_tags_removed(store: Store) -> None:
    track = full_track()
    store.add_track(track)
    store.update_track(dataclasses.replace(track, tags=("Dark",)))

    tags = store._db.execute("SELECT name FROM tags").fetchall()  # pyright: ignore[reportPrivateUsage]
    assert tags == [("Dark",)]
