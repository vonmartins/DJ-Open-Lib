"""Parsing real AcoustID and MusicBrainz answers (tests/fixtures/enrich)."""

import json
from typing import Any

import pytest

from support.enrich import FIXTURES, FakeClock, FakeTransport
from tunedex.enrich import EnrichError, acoustid, musicbrainz
from tunedex.enrich.cache import Cache
from tunedex.enrich.http import Client

LUNG_A = "73d6b7b1-2a6b-42b9-b92b-575774a70180"
LUNG_B = "bf6253d6-1245-4d94-a0b2-22a870f1614b"
INSIDERS = "6340a9b8-f427-4d89-a842-971a52ad3ce4"
METAFICTION = "98efe856-2747-4ffc-845a-8f7e97cd6afa"


def load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_one_recording() -> None:
    result = acoustid.parse(load("acoustid-dfrnt.json"))

    (candidate,) = result.candidates
    assert (candidate.title, candidate.artist) == ("Headspace (Scuba remix)", "DFRNT")
    assert candidate.score > 0.98 and candidate.duration == pytest.approx(370.88)


def test_duplicate_recordings() -> None:
    result = acoustid.parse(load("acoustid-lung.json"))

    assert {c.recording_id for c in result.candidates} == {LUNG_A, LUNG_B}
    assert {c.title for c in result.candidates} == {"Afterlife (Kryptic Minds remix)"}


def test_recognized_but_unlinked() -> None:
    result = acoustid.parse(load("acoustid-irrelevant.json"))

    assert result.best_score > 0.9 and result.candidates == ()


def test_not_recognized() -> None:
    assert acoustid.parse(load("acoustid-marina.json")) == acoustid.Lookup(0.0, ())


def test_acoustid_error() -> None:
    with pytest.raises(EnrichError, match="invalid API key"):
        acoustid.parse({"status": "error", "error": {"code": 4, "message": "invalid API key"}})


def test_lookup_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUNEDEX_ACOUSTID_KEY", "testkey")
    transport, clock = FakeTransport(), FakeClock()
    transport.route(acoustid.LOOKUP, lambda url, data: load("acoustid-dfrnt.json"))
    client = Client(transport, Cache(None), clock=clock, sleep=clock.sleep)

    acoustid.lookup(client, 370.6, "AQAAfp")

    method, url, data, _headers = transport.requests[0]
    assert (method, url) == ("POST", acoustid.LOOKUP)
    assert data is not None and data["client"] == "testkey" and data["duration"] == "371"


def test_key_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUNEDEX_ACOUSTID_KEY", raising=False)
    assert acoustid.key() == acoustid.ACOUSTID_KEY


def test_recording_with_a_featured_credit() -> None:
    recording = musicbrainz.parse_recording(load(f"recording-{INSIDERS}.json"))

    assert (recording.title, recording.artist) == ("Insiders", "Black Sun Empire feat. Optiv")
    assert recording.isrcs == ("NLCF10700011",)
    assert recording.genres[0] == ("drum and bass", 1)
    assert recording.remixers == ()  # only producer relations
    assert len(recording.artist_ids) == 2


def test_remix_title_without_relation() -> None:
    recording = musicbrainz.parse_recording(load(f"recording-{LUNG_A}.json"))

    assert recording.title == "Afterlife (Kryptic Minds remix)"
    assert recording.remixers == ()
    assert [(r.title, r.status, r.date) for r in recording.releases] == [
        ("Pure Dubstep", "Official", "2010-12-20")
    ]


def test_remixer_relation() -> None:
    data = {
        "id": "r",
        "title": "T (X remix)",
        "artist-credit": [{"name": "A", "joinphrase": "", "artist": {"id": "a"}}],
        "relations": [
            {"type": "remixer", "direction": "backward", "artist": {"id": "x", "name": "X"}},
            {"type": "producer", "artist": {"id": "p", "name": "P"}},
        ],
    }

    assert musicbrainz.parse_recording(data).remixers == ("X",)


def test_release() -> None:
    release = musicbrainz.parse_release(load(f"release-{METAFICTION}.json"))

    assert (release.title, release.date, release.artist) == ("Metafiction", "2009-09", "DFRNT")
    assert (release.label, release.catalog_number) == ("On The Edge", "OTECD001")
    scuba_remix = "b03469f1-8ae8-4e57-a73d-1bb81db98783"
    assert release.positions[scuba_remix] == (2, 9)  # the remix is on the second disc


def test_unexpected_answers() -> None:
    with pytest.raises(EnrichError):
        musicbrainz.parse_recording({"error": "Not Found"})
    with pytest.raises(EnrichError):
        musicbrainz.parse_release([])


def test_no_label() -> None:
    data: Any = load("release-98efe856-2747-4ffc-845a-8f7e97cd6afa.json")
    data["label-info"][0]["label"]["name"] = "[no label]"

    assert musicbrainz.parse_release(data).label is None
