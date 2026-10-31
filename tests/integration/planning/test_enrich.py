"""Planning and applying enrichment (specs/metadata-enrich)."""

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from support.enrich import FakeClock, FakeFpcalc, FakeTransport, answer, catalogue, fixture
from tunedex.enrich import EnrichError
from tunedex.enrich.cache import Cache
from tunedex.enrich.http import TransportError
from tunedex.enrich.service import Services
from tunedex.model.track import Track
from tunedex.planning import Engine, assume_yes, render_text
from tunedex.store import Store

DFRNT = "b03469f1-8ae8-4e57-a73d-1bb81db98783"
INSIDERS = "6340a9b8-f427-4d89-a842-971a52ad3ce4"
# Not recorded: the earliest release of Insiders, reduced to what mapping reads.
INSIDERS_RELEASE = {
    "id": "ce1bcc17-36c4-4b90-80f4-de47a4d1e376",
    "title": "Insiders / Hydroflash",
    "date": "2004-08-09",
    "media": [],
}
LOOKUPS: dict[str, Any] = {
    "fp-dfrnt": fixture("acoustid-dfrnt.json"),
    "fp-lung": fixture("acoustid-lung.json"),
    "fp-irrelevant": fixture("acoustid-irrelevant.json"),
    "fp-marina": fixture("acoustid-marina.json"),
    "fp-insiders": answer(INSIDERS, title="Insiders", duration=420),
    "fp-two": {
        "status": "ok",
        "results": [
            {"score": 0.95, "recordings": [{"id": DFRNT, "title": "Headspace", "duration": 371}]},
            {"score": 0.94, "recordings": [{"id": INSIDERS, "title": "Insiders", "duration": 370}]},
        ],
    },
}
PRINTS = {
    "dfrnt.mp3": (370.9, "fp-dfrnt"),
    "lung.mp3": (360.5, "fp-lung"),
    "irrelevant.mp3": (300.0, "fp-irrelevant"),
    "marina.mp3": (200.0, "fp-marina"),
    "insiders.mp3": (419.6, "fp-insiders"),
    "two.mp3": (370.5, "fp-two"),
}


@dataclasses.dataclass
class World:
    store: Store
    engine: Engine
    music: Path
    cache: Cache
    fpcalc: FakeFpcalc
    transport: FakeTransport

    def services(self, transport: FakeTransport | None = None) -> Services:
        clock = FakeClock()
        return Services.create(
            self.cache,
            transport=transport or self.transport,
            clock=clock,
            sleep=clock.sleep,
            run=self.fpcalc,
            which=lambda _name: "/usr/bin/fpcalc",
        )

    def add(self, name: str, **fields: Any) -> Track:
        path = self.music / name
        path.write_bytes(b"audio")
        track = Track(path_origin=str(path), **fields)
        self.store.add_track(track)
        return track

    def plan(self, **kwargs: Any) -> Any:
        return self.engine.plan_enrich(self.services(), **kwargs)


@pytest.fixture
def world(engine: Engine, store: Store, tmp_path: Path) -> World:
    music = tmp_path / "music"
    music.mkdir()
    cache = Cache(tmp_path / "cache.db")
    transport = catalogue(LOOKUPS)
    transport.routes.insert(
        0, ("https://musicbrainz.org/ws/2/release/ce1bcc17", lambda *_: INSIDERS_RELEASE)
    )
    return World(store, engine, music, cache, FakeFpcalc(dict(PRINTS)), transport)


def test_first_run_normalizes(world: World) -> None:
    track = world.add("dfrnt.mp3", artist="dfrnt", title="headspace scuba rmx [HQ]", year=2015)

    plan = world.plan()

    (change,) = plan.tracks
    fields = {f.field: f.after for f in change.fields}
    assert fields["title"] == "Headspace (Scuba remix)"
    assert fields["year"] == 2009
    assert (fields["album"], fields["label"], fields["remixer"]) == (
        "Metafiction",
        "On The Edge",
        "Scuba",
    )
    assert (fields["disc_number"], fields["track_number"]) == (2, 9)
    assert {f.by for f in change.fields} == {"musicbrainz"}
    assert "(musicbrainz)" in render_text(plan)
    assert plan.warnings[0].startswith("musicbrainz: 1 identified")

    world.engine.apply(plan, assume_yes)
    enriched = world.store.get_track(track.id)
    assert enriched.unmapped["musicbrainz"]["recording_id"] == DFRNT  # type: ignore[index]
    assert world.plan().empty


def test_duplicates_settle(world: World) -> None:
    world.add("dfrnt.mp3", title="x")
    (world.music / "copy").mkdir()
    world.add("copy/dfrnt.mp3", title="x")

    world.engine.apply(world.plan(), assume_yes)

    assert {t.title for t in world.store.list_tracks()} == {"Headspace (Scuba remix)"}
    assert world.plan().empty


def test_planned_enrichment_changes_nothing(world: World) -> None:
    world.add("dfrnt.mp3", title="x")
    revision, before = world.store.revision(), world.store.load_library()

    world.plan()

    assert (world.store.revision(), world.store.load_library()) == (revision, before)


def test_edit_kept(world: World) -> None:
    track = world.add("dfrnt.mp3", title="x")
    world.engine.apply(world.plan(), assume_yes)
    edited = dataclasses.replace(world.store.get_track(track.id), title="Headspace (my edit)")
    world.store.update_track(edited)

    plan = world.plan()

    assert plan.empty
    assert world.store.get_track(track.id).title == "Headspace (my edit)"


def test_second_plan_is_offline(world: World) -> None:
    world.add("dfrnt.mp3", title="x")
    first = world.plan()
    offline = FakeTransport()

    second = world.engine.plan_enrich(world.services(offline))

    assert second.tracks == first.tracks
    assert offline.requests == []
    assert len(world.fpcalc.calls) == 1


def test_refresh_asks_again(world: World, tmp_path: Path) -> None:
    world.add("dfrnt.mp3", title="x")
    world.plan()
    world.cache = Cache(tmp_path / "cache.db", refresh=True)
    offline = FakeTransport()

    with pytest.raises(EnrichError, match="cannot reach"):
        world.engine.plan_enrich(world.services(offline))
    assert offline.requests


def test_no_network(world: World) -> None:
    world.add("dfrnt.mp3", title="x")
    down = FakeTransport()
    for _ in range(4):
        down.queue("https://api.acoustid.org/", TransportError("no route to host"))

    with pytest.raises(EnrichError, match=r"cannot reach api\.acoustid\.org"):
        world.engine.plan_enrich(world.services(down))


def test_genre_not_replaced(world: World) -> None:
    kept = world.add("insiders.mp3", title="Insiders", genre="Neurofunk")

    (change,) = world.plan().tracks

    assert "genre" not in {f.field for f in change.fields}
    assert change.track_id == kept.id


def test_genre_filled_when_empty(world: World) -> None:
    world.add("insiders.mp3", title="Insiders")

    (change,) = world.plan().tracks

    fields = {f.field: f.after for f in change.fields}
    assert fields["genre"] == "Drum And Bass"
    assert fields["artist"] == "Black Sun Empire feat. Optiv"


def test_outcomes_reported(world: World) -> None:
    for name in ("lung.mp3", "irrelevant.mp3", "marina.mp3", "two.mp3"):
        world.add(name, title=name.removesuffix(".mp3"))
    world.store.add_track(Track(path_origin=str(world.music / "gone.mp3"), title="gone"))

    plan = world.plan()

    summary = plan.warnings[0]
    for count in (
        "1 identified",
        "1 unresolved",
        "1 recognized but not in MusicBrainz",
        "1 not recognized",
        "1 skipped (file missing)",
    ):
        assert count in summary
    assert any(w.startswith("unresolved ") and "Insiders" in w for w in plan.warnings)
    assert [c.name for c in plan.tracks] == ["lung"]

    world.engine.apply(plan, assume_yes)
    assert world.plan().warnings == ()


def test_disagreement_left_alone(world: World) -> None:
    other = "00000000-0000-4000-8000-000000000000"
    track = world.add("dfrnt.mp3", title="x", unmapped={"beets": {"mb_trackid": other}})

    plan = world.plan()

    assert plan.empty
    assert any(other in w and DFRNT in w for w in plan.warnings)
    assert world.store.get_track(track.id).title == "x"


def test_under_a_folder(world: World) -> None:
    world.add("dfrnt.mp3", title="x")
    elsewhere = world.music / "other"
    elsewhere.mkdir()
    (elsewhere / "insiders.mp3").write_bytes(b"audio")
    world.store.add_track(Track(path_origin=str(elsewhere / "insiders.mp3"), title="y"))

    plan = world.plan(under=elsewhere)

    assert [c.name for c in plan.tracks] == ["y"]


def test_progress(world: World) -> None:
    world.add("dfrnt.mp3", title="x")
    world.add("marina.mp3", title="y")
    seen: list[tuple[int, int]] = []

    world.plan(steps=lambda done, total: seen.append((done, total)))

    assert seen[-1] == (2, 2)
    assert seen[0] == (0, 2)


def test_fpcalc_missing(world: World) -> None:
    world.add("dfrnt.mp3", title="x")
    services = Services.create(world.cache, transport=world.transport, which=lambda _name: None)

    with pytest.raises(EnrichError, match="fpcalc"):
        world.engine.plan_enrich(services)
