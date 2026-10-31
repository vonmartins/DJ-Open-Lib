"""``tunedex enrich`` (specs/cli)."""

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from support.enrich import FakeClock, FakeFpcalc, FakeTransport, catalogue, fixture
from tunedex.cli import app
from tunedex.enrich.cache import Cache
from tunedex.enrich.service import Services
from tunedex.model.track import Track
from tunedex.store import Store

# The package exports the command function under the module's name.
command = importlib.import_module("tunedex.cli.enrich")
runner = CliRunner()
DFRNT = "b03469f1-8ae8-4e57-a73d-1bb81db98783"


def invoke(tmp_path: Path, *arguments: str) -> Result:
    return runner.invoke(app, ["--home", str(tmp_path / "home"), "enrich", *arguments])


def library(tmp_path: Path) -> Track:
    (tmp_path / "home").mkdir()
    file = tmp_path / "music" / "dfrnt.mp3"
    file.parent.mkdir()
    file.write_bytes(b"audio")
    track = Track(path_origin=str(file), artist="dfrnt", title="headspace")
    with Store.open(tmp_path / "home" / "library.db") as store:
        store.add_track(track)
    return track


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> FakeTransport:
    fake = catalogue({"fp-dfrnt": fixture("acoustid-dfrnt.json")})

    def services(cache: Cache) -> Services:
        clock = FakeClock()
        return Services.create(
            cache,
            transport=fake,
            clock=clock,
            sleep=clock.sleep,
            run=FakeFpcalc({"dfrnt.mp3": (370.9, "fp-dfrnt")}),
            which=lambda _name: "/usr/bin/fpcalc",
        )

    monkeypatch.setattr(command, "services", services)
    return fake


def titles(tmp_path: Path) -> list[str | None]:
    with Store.open(tmp_path / "home" / "library.db") as store:
        return [t.title for t in store.list_tracks()]


def test_dry_run(tmp_path: Path, transport: FakeTransport) -> None:
    library(tmp_path)

    result = invoke(tmp_path)

    assert result.exit_code == 0, result.stderr
    assert "Headspace (Scuba remix)" in result.stdout
    assert "(musicbrainz)" in result.stdout
    assert "Dry run" in result.stdout
    assert titles(tmp_path) == ["headspace"]
    assert (tmp_path / "home" / "cache.db").exists()


def test_applied_then_offline(tmp_path: Path, transport: FakeTransport) -> None:
    library(tmp_path)
    assert invoke(tmp_path, "--apply", "--yes").exit_code == 0
    assert titles(tmp_path) == ["Headspace (Scuba remix)"]
    asked = len(transport.requests)

    result = invoke(tmp_path, "--json")

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["tracks"] == []
    assert len(transport.requests) == asked


def test_refresh(tmp_path: Path, transport: FakeTransport) -> None:
    library(tmp_path)
    invoke(tmp_path)
    asked = len(transport.requests)

    assert invoke(tmp_path, "--refresh").exit_code == 0
    assert len(transport.requests) > asked


def test_key_from_the_environment(
    tmp_path: Path, transport: FakeTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    library(tmp_path)
    monkeypatch.setenv("TUNEDEX_ACOUSTID_KEY", "my-key")

    assert invoke(tmp_path).exit_code == 0
    posted: Any = [data for _method, _url, data, _headers in transport.requests if data]
    assert posted[0]["client"] == "my-key"


def test_fpcalc_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library(tmp_path)
    monkeypatch.setattr(
        command, "services", lambda cache: Services.create(cache, which=lambda _name: None)
    )

    result = invoke(tmp_path)

    assert result.exit_code == 1
    (line,) = result.stderr.splitlines()
    assert line.startswith("error: fpcalc (Chromaprint) is needed")


def test_no_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library(tmp_path)

    def services(cache: Cache) -> Services:
        clock = FakeClock()
        return Services.create(
            cache,
            clock=clock,
            sleep=clock.sleep,
            run=FakeFpcalc({"dfrnt.mp3": (370.9, "fp-dfrnt")}),
            which=lambda _name: "/usr/bin/fpcalc",
        )

    monkeypatch.setattr(command, "services", services)

    result = invoke(tmp_path)

    assert result.exit_code == 1
    assert "cannot reach api.acoustid.org" in result.stderr
    assert titles(tmp_path) == ["headspace"]


def test_under_must_be_a_folder(tmp_path: Path) -> None:
    library(tmp_path)

    result = invoke(tmp_path, "--under", str(tmp_path / "nowhere"))

    assert result.exit_code == 1
    assert "nowhere does not exist" in result.stderr


def test_new_home_creates_nothing(tmp_path: Path, transport: FakeTransport) -> None:
    result = invoke(tmp_path)

    assert result.exit_code == 0, result.stderr
    assert not (tmp_path / "home").exists()
