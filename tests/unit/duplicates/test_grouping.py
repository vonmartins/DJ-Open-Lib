"""Duplicate groups and the suggested track (specs/duplicates)."""

import datetime
import random
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tunedex.duplicates.grouping import find_groups
from tunedex.duplicates.ranking import Facts, rank
from tunedex.model.beatgrid import BeatGrid, BeatMarker
from tunedex.model.cue import Cue, CueKind
from tunedex.model.ids import TrackId
from tunedex.model.track import Track

RECORDING = "b03469f1-8ae8-4e57-a73d-1bb81db98783"


def track(name: str, seconds: float | None = 312, **fields: Any) -> Track:
    fields.setdefault("artist", "Phaeleh")
    fields.setdefault("title", "Numb")
    duration = None if seconds is None else round(seconds * 1_000_000)
    return Track(path_origin=f"/music/{name}", duration_us=duration, **fields)


def paths(groups: list[list[Track]]) -> list[list[str]]:
    return sorted(sorted(t.path.rsplit("/", 1)[-1] for t in g) for g in groups)


def test_same_recording() -> None:
    mb = {"musicbrainz": {"recording_id": RECORDING}}
    beets = {"beets": {"mb_trackid": RECORDING}}
    tracks = [
        track("a.mp3", title="Headspace", unmapped=mb),
        track("b.mp3", title="Headspace (Scuba remix)", seconds=500, unmapped=beets),
    ]

    assert paths(find_groups(tracks)) == [["a.mp3", "b.mp3"]]


def test_same_tags_close_lengths() -> None:
    assert paths(find_groups([track("a.mp3", 312), track("b.mp3", 310)])) == [["a.mp3", "b.mp3"]]


def test_lengths_too_far_apart() -> None:
    assert find_groups([track("a.mp3", 312), track("b.mp3", 420)]) == []


def test_three_copies() -> None:
    tracks = [track("a.mp3", 312), track("b.flac", 311), track("c.mp3", 313.5)]

    assert paths(find_groups(tracks)) == [["a.mp3", "b.flac", "c.mp3"]]


def test_unknown_length_joins() -> None:
    tracks = [track("a.mp3", 312), track("b.mp3", None), track("c.mp3", 420)]

    assert paths(find_groups(tracks)) == [["a.mp3", "b.mp3"]]


def test_other_songs_not_grouped() -> None:
    tracks = [track("a.mp3"), track("b.mp3", title="Afterlife"), track("c.mp3", artist=None)]

    assert find_groups(tracks) == []


@given(st.randoms())
def test_order_does_not_matter(rng: random.Random) -> None:
    tracks = [
        track("a.mp3", 312),
        track("b.mp3", 314),
        track("c.mp3", 318),
        track("d.mp3", None),
        track("e.mp3", 200, title="Lounge"),
        track("f.mp3", 201, title="Lounge (feat. Anneka)"),
        track("g.mp3", 202, artist="Phaeleh feat. Anneka", title="Lounge"),
    ]
    shuffled = tracks[:]
    rng.shuffle(shuffled)

    assert paths(find_groups(shuffled)) == paths(find_groups(tracks))


def facts(
    *tracks: Track, missing: tuple[Track, ...] = (), playlists: int = 0
) -> dict[TrackId, Facts]:
    return {t.id: Facts(present=t not in missing, playlists=playlists) for t in tracks}


GRID = BeatGrid(markers=(BeatMarker(position_us=0, bpm=140.0),))
CUE = Cue(kind=CueKind.HOT, start_us=0, slot=0)


@pytest.mark.parametrize(
    ("best", "other", "reason"),
    [
        (dict(file_format="flac"), dict(file_format="mp3", bitrate=320), "lossless"),
        (dict(file_format="mp3", bitrate=320), dict(file_format="mp3", bitrate=128), "bitrate"),
        (dict(bitrate=320, cues=(CUE,)), dict(bitrate=320), "cues"),
        (dict(bitrate=320), dict(bitrate=320, date_added=datetime.date(2020, 1, 1)), "oldest"),
        (dict(), dict(), "path"),
    ],
)
def test_suggestion(best: dict[str, Any], other: dict[str, Any], reason: str) -> None:
    kept, dropped = track("a.mp3", **best), track("b.mp3", **other)
    if reason == "oldest":
        kept = track("z.mp3", date_added=datetime.date(2019, 1, 1), **best)

    ranked = rank([dropped, kept], facts(kept, dropped))

    assert (ranked.tracks[0], ranked.reason) == (kept, reason)


def test_beat_grid_and_playlists() -> None:
    gridded, plain = track("b.mp3", beatgrid=GRID), track("a.mp3")
    assert rank([plain, gridded], facts(plain, gridded)).reason == "beat grid"

    listed, other = track("b.mp3"), track("a.mp3")
    known = {listed.id: Facts(True, 2), other.id: Facts(True, 0)}
    assert rank([other, listed], known).tracks[0] == listed


def test_missing_file_not_kept() -> None:
    flac, mp3 = track("a.flac", file_format="flac"), track("b.mp3", file_format="mp3")

    ranked = rank([flac, mp3], facts(flac, mp3, missing=(flac,)))

    assert (ranked.tracks[0], ranked.reason) == (mp3, "file present")
    all_missing = rank([flac, mp3], facts(flac, mp3, missing=(flac, mp3)))
    assert all_missing.tracks[0] == flac
