"""MusicBrainz data as track fields (specs/metadata-enrich)."""

import datetime
import json

from support.enrich import FIXTURES
from tunedex.enrich import musicbrainz
from tunedex.enrich.mapping import choose_release, first_release_date, map_recording
from tunedex.enrich.musicbrainz import Recording, ReleaseRef

DFRNT = "b03469f1-8ae8-4e57-a73d-1bb81db98783"
LUNG = "73d6b7b1-2a6b-42b9-b92b-575774a70180"
INSIDERS = "6340a9b8-f427-4d89-a842-971a52ad3ce4"


def load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def recording(id_: str) -> Recording:
    return musicbrainz.parse_recording(load(f"recording-{id_}.json"))


def releases(*refs: tuple[str, str, str | None, str | None]) -> Recording:
    return Recording("r", "T", "A", (), None, (), (), (), tuple(ReleaseRef(*r) for r in refs))


def test_album_kept() -> None:
    rec = releases(("1", "Hits", "Official", "2019"), ("2", "Isles", "Official", "2021-01-22"))

    assert choose_release(rec, "isles").id == "2"  # type: ignore[union-attr]


def test_earliest_release() -> None:
    rec = releases(
        ("1", "Later", "Official", "2021"),
        ("2", "Earlier", "Official", "2019-05"),
        ("3", "Bootleg", "Bootleg", "2001"),
        ("4", "Undated", "Official", None),
    )

    assert choose_release(rec, None).id == "2"  # type: ignore[union-attr]
    assert first_release_date(rec) == "2019-05"


def test_no_official_release() -> None:
    assert choose_release(releases(("1", "Promo", "Promotion", "2019")), None) is None


def test_dfrnt_on_its_first_release() -> None:
    rec = recording(DFRNT)
    ref = choose_release(rec, None)
    assert ref is not None and ref.title == "Metafiction"
    release = musicbrainz.parse_release(load(f"release-{ref.id}.json"))

    mapped = map_recording(rec, release, score=0.99)

    assert mapped.fields == {
        "title": "Headspace (Scuba remix)",
        "artist": "DFRNT",
        "remixer": "Scuba",
        "album": "Metafiction",
        "album_artist": "DFRNT",
        "year": 2009,
        "label": "On The Edge",
        "disc_number": 2,
        "track_number": 9,
    }
    assert mapped.unmapped["catalog_number"] == "OTECD001"
    assert mapped.unmapped["recording_id"] == DFRNT


def test_remix_identified() -> None:
    rec = recording(LUNG)
    ref = choose_release(rec, None)
    assert ref is not None
    release = musicbrainz.parse_release(load(f"release-{ref.id}.json"))

    mapped = map_recording(rec, release, score=0.97)

    assert mapped.fields["title"] == "Afterlife (Kryptic Minds remix)"
    assert mapped.fields["remixer"] == "Kryptic Minds"
    assert mapped.fields["album_artist"] == "Various Artists"
    assert mapped.fields["release_date"] == datetime.date(2010, 12, 20)


def test_identifiers_and_genre() -> None:
    mapped = map_recording(recording(INSIDERS), None, score=0.97)

    assert mapped.fields == {"title": "Insiders", "artist": "Black Sun Empire feat. Optiv"}
    assert mapped.genre == "Drum And Bass"
    assert mapped.unmapped["isrcs"] == ["NLCF10700011"]
    assert len(mapped.unmapped["artist_ids"]) == 2  # type: ignore[arg-type]


def test_remixer_relation_wins_over_the_title() -> None:
    rec = Recording("r", "T (Y Remix)", "A", (), None, (), ("X",), (), ())

    assert map_recording(rec, None, score=1.0).fields["remixer"] == "X"
