"""Hypothesis strategies and deterministic factories for valid model values."""

import datetime
import random
import unicodedata
import uuid

from hypothesis import strategies as st

from djlib.model.beatgrid import BeatGrid, BeatMarker
from djlib.model.cue import Cue, CueKind
from djlib.model.ids import NodeId, TrackId
from djlib.model.key import Key, Mode
from djlib.model.library import Library
from djlib.model.playlist import Folder, MatchMode, Node, Playlist, Rule, Smartlist
from djlib.model.track import Track
from djlib.model.unmapped import JSONValue

# Lone surrogates cannot be stored as UTF-8 text, so they are excluded here.
text = st.text(st.characters(exclude_categories=("Cs",)), max_size=20)
optional_text = st.none() | text
names = st.text(st.characters(exclude_categories=("Cs",)), min_size=1, max_size=12)
# One path component: no separators, NUL, "." or "..".
path_segments = st.text(
    st.characters(exclude_categories=("Cs",), exclude_characters="\0/\\"), min_size=1, max_size=12
).filter(lambda s: s not in {".", ".."})
microseconds = st.integers(min_value=0, max_value=2**40)
bpms = st.floats(min_value=1.0, max_value=999.0, allow_nan=False, allow_infinity=False)
colors = st.from_regex(r"\A#[0-9A-F]{6}\Z")
keys = st.builds(Key, tonic=st.integers(0, 11), mode=st.sampled_from(Mode))
dates = st.dates(min_value=datetime.date(1900, 1, 1), max_value=datetime.date(2100, 12, 31))
datetimes = st.datetimes(
    min_value=datetime.datetime(1900, 1, 1), max_value=datetime.datetime(2100, 12, 31)
)

json_scalars = st.none() | st.booleans() | st.integers(-(2**53), 2**53) | text
json_floats = st.floats(allow_nan=False, allow_infinity=False)
json_values: st.SearchStrategy[JSONValue] = st.recursive(
    json_scalars | json_floats,
    lambda children: st.lists(children, max_size=3) | st.dictionaries(text, children, max_size=3),
    max_leaves=6,
)
unmapped = st.dictionaries(names, json_values, max_size=2)


@st.composite
def cues(draw: st.DrawFn) -> tuple[Cue, ...]:
    count = draw(st.integers(0, 6))
    slots = draw(st.lists(st.integers(0, 15), min_size=count, max_size=count, unique=True))
    result: list[Cue] = []
    for slot in slots:
        kind = draw(st.sampled_from(CueKind))
        start = draw(microseconds)
        loop = kind is CueKind.LOOP
        result.append(
            Cue(
                kind=kind,
                start_us=start,
                slot=None if kind is CueKind.MEMORY else draw(st.none() | st.just(slot)),
                name=draw(optional_text),
                color=draw(st.none() | colors),
                end_us=start + draw(st.integers(1, 10**9)) if loop else None,
                active=draw(st.booleans()) if loop else False,
                unmapped=draw(unmapped),
            )
        )
    return tuple(result)


@st.composite
def beatgrids(draw: st.DrawFn) -> BeatGrid:
    positions = sorted(draw(st.sets(microseconds, min_size=1, max_size=4)))
    markers = tuple(
        BeatMarker(position_us=p, bpm=draw(bpms), beat=draw(st.integers(1, 4))) for p in positions
    )
    return BeatGrid(markers=markers)


@st.composite
def tracks(draw: st.DrawFn, path: str | None = None) -> Track:
    small = st.none() | st.integers(0, 10)
    count = st.none() | st.integers(0, 2**31)
    return Track(
        path_origin=path or "/music/" + draw(path_segments),
        title=draw(optional_text),
        artist=draw(optional_text),
        album=draw(optional_text),
        genre=draw(optional_text),
        comment=draw(optional_text),
        remixer=draw(optional_text),
        label=draw(optional_text),
        file_format=draw(optional_text),
        extra1=draw(optional_text),
        year=draw(st.none() | st.integers(0, 9999)),
        track_number=draw(count),
        disc_number=draw(count),
        bpm=draw(st.none() | bpms),
        key=draw(st.none() | keys),
        key_original=draw(optional_text),
        rating=draw(st.none() | st.integers(0, 5)),
        color=draw(st.none() | colors),
        play_count=draw(count),
        date_added=draw(st.none() | dates),
        release_date=draw(st.none() | dates),
        last_played=draw(st.none() | datetimes),
        duration_us=draw(st.none() | microseconds),
        bitrate=draw(count),
        sample_rate=draw(count),
        energy=draw(small),
        danceability=draw(small),
        happiness=draw(small),
        popularity=draw(small),
        tags=tuple(draw(st.lists(names, max_size=4))),
        cues=draw(cues()),
        beatgrid=draw(st.none() | beatgrids()),
        unmapped=draw(unmapped),
    )


rules = st.builds(
    Rule, field=names, operator=names, values=st.lists(json_values, max_size=3).map(tuple)
)


def nodes(track_ids: list[TrackId], depth: int = 2) -> st.SearchStrategy[Node]:
    entries = st.lists(st.sampled_from(track_ids), max_size=5) if track_ids else st.just([])
    playlist = st.builds(Playlist, name=text, entries=entries.map(tuple), unmapped=unmapped)
    smartlist = st.builds(
        Smartlist,
        name=text,
        match=st.sampled_from(MatchMode),
        rules=st.lists(rules, max_size=3).map(tuple),
    )
    leaf = playlist | smartlist
    if depth == 0:
        return leaf
    folder = st.builds(
        Folder, name=text, children=st.lists(nodes(track_ids, depth - 1), max_size=3).map(tuple)
    )
    return leaf | folder


@st.composite
def libraries(draw: st.DrawFn) -> Library:
    nfc = lambda segment: unicodedata.normalize("NFC", segment)  # noqa: E731
    segments = draw(st.lists(path_segments, max_size=8, unique_by=nfc))
    library_tracks = [draw(tracks(path="/music/" + segment)) for segment in segments]
    roots = draw(st.lists(nodes([t.id for t in library_tracks]), max_size=4))
    return Library.build(library_tracks, roots)


def synthetic_library(track_count: int, seed: int = 0) -> Library:
    """A deterministic library with cues, beatgrids, tags and nested playlists."""
    rng = random.Random(seed)

    def node_id() -> uuid.UUID:
        return uuid.UUID(int=rng.getrandbits(128), version=4)

    genres = ["Techno", "House", "Drum & Bass", "Disco", "Ambient"]
    library_tracks: list[Track] = []
    for i in range(track_count):
        start = rng.randrange(0, 30_000_000)
        library_tracks.append(
            Track(
                id=TrackId(node_id()),
                path_origin=f"/music/{genres[i % 5]}/{i:06d} - Artist {i % 97}.mp3",
                title=f"Track {i}",
                artist=f"Artist {i % 97}",
                genre=genres[i % 5],
                bpm=round(rng.uniform(80, 180), 3),
                key=Key.from_code(rng.randrange(24)),
                key_original=None,
                rating=rng.randrange(6),
                duration_us=rng.randrange(120_000_000, 600_000_000),
                date_added=datetime.date(2020, 1, 1) + datetime.timedelta(days=i % 2000),
                tags=tuple(rng.sample(["Vocals", "Peak", "Warmup", "Dark", "Groovy"], 2)),
                cues=(
                    Cue(kind=CueKind.HOT, start_us=start, slot=0, name="Intro"),
                    Cue(kind=CueKind.MEMORY, start_us=start + 64_000_000),
                    Cue(kind=CueKind.LOOP, start_us=start, end_us=start + 7_500_000, slot=1),
                ),
                beatgrid=BeatGrid(markers=(BeatMarker(position_us=start, bpm=128.0),)),
            )
        )

    ids = [t.id for t in library_tracks]
    folders: list[Node] = []
    for f in range(10):
        lists = tuple(
            Playlist(
                id=NodeId(node_id()),
                name=f"List {f}.{p}",
                entries=tuple(rng.sample(ids, min(50, len(ids)))),
            )
            for p in range(5)
        )
        inner = Folder(id=NodeId(node_id()), name=f"Sub {f}", children=lists[:2])
        folders.append(
            Folder(id=NodeId(node_id()), name=f"Folder {f}", children=(inner, *lists[2:]))
        )
    folders.append(
        Smartlist(
            id=NodeId(node_id()),
            name="Techno",
            rules=(Rule(field="genre", operator="is", values=("Techno",)),),
        )
    )
    return Library.build(library_tracks, folders)
