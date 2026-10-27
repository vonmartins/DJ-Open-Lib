from djlib.adapters.contract import Capabilities
from djlib.adapters.losses import compute_losses, display_name
from djlib.model.beatgrid import BeatGrid, BeatMarker
from djlib.model.cue import Cue, CueKind
from djlib.model.library import Library
from djlib.model.playlist import Folder, Playlist, Smartlist
from djlib.model.track import Track

BASIC = Capabilities(track_fields=frozenset({"title", "artist"}))


def track(n: int, **fields: object) -> Track:
    return Track(path_origin=f"/m/{n:02d}.mp3", title=f"T{n}", artist="A", **fields)  # pyright: ignore[reportArgumentType]


def test_cues_lost_with_count_and_examples() -> None:
    tracks = [track(n, cues=(Cue(kind=CueKind.HOT, start_us=0, slot=0),)) for n in range(7)]
    library = Library.build(tracks)

    losses = compute_losses(library, [t.id for t in tracks], [], BASIC, "m3u").losses()

    (loss,) = [loss for loss in losses if loss.kind == "cue:hot"]
    assert loss.count == 7
    assert loss.examples == ("A - T0", "A - T1", "A - T2", "A - T3", "A - T4")


def test_nothing_lost() -> None:
    tracks = [track(1), track(2)]
    library = Library.build(tracks, [Playlist(name="p", entries=(tracks[0].id, tracks[1].id))])

    assert (
        compute_losses(library, [t.id for t in tracks], library.playlists, BASIC, "m3u").losses()
        == ()
    )


def test_fields_beatgrid_tags_and_other_formats() -> None:
    rich = track(
        1,
        bpm=128.0,
        rating=4,
        tags=("Peak",),
        beatgrid=BeatGrid(markers=(BeatMarker(position_us=0, bpm=128.0),)),
        unmapped={"traktor": {"LOCK": "1"}, "m3u": {"x": 1}},
    )
    library = Library.build([rich])

    kinds = {
        loss.kind: loss.count
        for loss in compute_losses(library, [rich.id], [], BASIC, "m3u").losses()
    }

    assert kinds == {
        "field:rating": 1,
        "field:bpm": 1,
        "beatgrid": 1,
        "tags": 1,
        "unmapped:traktor": 1,
    }


def test_supported_cue_kinds_not_reported() -> None:
    caps = Capabilities(
        track_fields=frozenset({"title", "artist"}), cue_kinds=frozenset({CueKind.HOT})
    )
    t = track(
        1, cues=(Cue(kind=CueKind.HOT, start_us=0, slot=0), Cue(kind=CueKind.MEMORY, start_us=5))
    )

    kinds = [
        loss.kind for loss in compute_losses(Library.build([t]), [t.id], [], caps, "x").losses()
    ]

    assert kinds == ["cue:memory"]


def test_smartlists_folders_and_tracks_outside_playlists() -> None:
    inside, outside = track(1), track(2)
    smart = Smartlist(name="Smart")
    folder = Folder(name="F", children=(Playlist(name="P", entries=(inside.id,)),))
    library = Library.build([inside, outside], [folder, smart])

    losses = {
        loss.kind: loss
        for loss in compute_losses(library, [inside.id], [folder, smart], BASIC, "x").losses()
    }

    assert losses["smartlists"].examples == ("Smart",)
    assert losses["folders"].examples == ("F",)
    assert losses["tracks-outside-playlists"].examples == ("A - T2",)


def test_repeated_track_counted_once() -> None:
    t = track(1, rating=3)
    kinds = compute_losses(Library.build([t]), [t.id, t.id], [], BASIC, "x").losses()
    assert [(loss.kind, loss.count) for loss in kinds] == [("field:rating", 1)]


def test_display_name_fallbacks() -> None:
    assert display_name(Track(path_origin="/m/Some File.mp3")) == "Some File.mp3"
    assert display_name(Track(path_origin="/m/a.mp3", title="Only")) == "Only"
