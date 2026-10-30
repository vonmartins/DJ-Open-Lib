from pathlib import Path

from tunedex.adapters.m3u import M3UAdapter
from tunedex.model.beatgrid import BeatGrid, BeatMarker
from tunedex.model.cue import Cue, CueKind
from tunedex.model.library import Library
from tunedex.model.playlist import Playlist, Smartlist
from tunedex.model.track import Track


def test_m3u_capabilities() -> None:
    caps = M3UAdapter().capabilities
    assert caps.track_fields == {"title", "artist", "duration_us"}
    assert (caps.folders, caps.smartlists, caps.beatgrid, caps.tags, caps.collection) == (
        True,
        False,
        False,
        False,
        False,
    )
    assert caps.cue_kinds == frozenset()


def test_every_m3u_loss_reported(tmp_path: Path) -> None:
    rich = Track(
        path_origin="/music/rich.mp3",
        artist="A",
        title="Rich",
        duration_us=372_400_000,
        bpm=128.0,
        rating=5,
        tags=("Peak",),
        cues=(
            Cue(kind=CueKind.HOT, start_us=0, slot=0),
            Cue(kind=CueKind.MEMORY, start_us=10),
            Cue(kind=CueKind.LOOP, start_us=0, end_us=100),
        ),
        beatgrid=BeatGrid(markers=(BeatMarker(position_us=0, bpm=128.0),)),
        unmapped={"traktor": {"LOCK": "1"}},
    )
    lonely = Track(path_origin="/music/lonely.mp3", title="Lonely")
    library = Library.build(
        [rich, lonely], [Playlist(name="P", entries=(rich.id,)), Smartlist(name="S")]
    )

    plan = M3UAdapter().plan_write(library, tmp_path)

    assert {loss.kind: loss.count for loss in plan.losses} == {
        "duration-rounded": 1,
        "field:rating": 1,
        "field:bpm": 1,
        "cue:hot": 1,
        "cue:memory": 1,
        "cue:loop": 1,
        "beatgrid": 1,
        "tags": 1,
        "unmapped:traktor": 1,
        "smartlists": 1,
        "tracks-outside-playlists": 1,
    }


def test_whole_second_durations_not_reported(tmp_path: Path) -> None:
    track = Track(path_origin="/music/a.mp3", title="T", duration_us=300_000_000)
    library = Library.build([track], [Playlist(name="P", entries=(track.id,))])

    assert M3UAdapter().plan_write(library, tmp_path).losses == ()
