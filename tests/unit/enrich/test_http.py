import pytest

from djlib.enrich import EnrichError
from djlib.enrich.cache import Cache
from djlib.enrich.http import Client, Response, TransportError
from support.enrich import FakeClock, FakeTransport, ok

MB = "https://musicbrainz.org/ws/2/recording/x"


def client(transport: FakeTransport, clock: FakeClock, cache: Cache | None = None) -> Client:
    return Client(
        transport,
        cache or Cache(None),
        intervals={"musicbrainz.org": 1.0, "api.acoustid.org": 0.34},
        clock=clock,
        sleep=clock.sleep,
        agent="djlib/test",
    )


def test_rate_limit_per_host() -> None:
    transport, clock = FakeTransport(), FakeClock()
    transport.route("https://musicbrainz.org", lambda url, data: {"url": url})
    http = client(transport, clock)

    for n in range(3):
        http.get(MB, {"n": str(n)})

    assert clock.slept == [1.0, 1.0]
    assert transport.requests[0][3]["User-Agent"] == "djlib/test"


def test_retries_on_busy_and_timeouts() -> None:
    transport, clock = FakeTransport(), FakeClock()
    transport.queue(MB, Response(503, b"busy"), TransportError("timed out"), ok({"id": "x"}))

    assert client(transport, clock).get(MB, {}) == {"id": "x"}
    assert len(transport.requests) == 3


def test_gives_up_after_three_attempts() -> None:
    transport, clock = FakeTransport(), FakeClock()
    transport.queue(MB, *(Response(429, b"slow down") for _ in range(3)))

    with pytest.raises(EnrichError, match=r"musicbrainz.org answered 429; try again later"):
        client(transport, clock).get(MB, {})


def test_no_network() -> None:
    transport, clock = FakeTransport(), FakeClock()
    transport.queue(MB, *(TransportError("Name or service not known") for _ in range(3)))

    with pytest.raises(EnrichError, match=r"cannot reach musicbrainz.org"):
        client(transport, clock).get(MB, {})


def test_client_errors_are_not_retried() -> None:
    transport, clock = FakeTransport(), FakeClock()
    transport.queue(MB, Response(400, b"bad request"))

    with pytest.raises(EnrichError, match=r"answered 400: bad request"):
        client(transport, clock).get(MB, {})
    assert len(transport.requests) == 1


def test_cache_hits_and_refresh() -> None:
    transport, clock = FakeTransport(), FakeClock()
    transport.route("https://musicbrainz.org", lambda url, data: {"n": len(transport.requests)})
    cache = Cache(None)
    http = client(transport, clock, cache)

    first = http.get(MB, {"inc": "a"})
    assert http.get(MB, {"inc": "a"}) == first
    assert len(transport.requests) == 1

    cache.refresh = True
    assert http.get(MB, {"inc": "a"}) != first
    assert len(transport.requests) == 2


def test_post_keeps_secrets_out_of_the_cache_key() -> None:
    transport, clock = FakeTransport(), FakeClock()
    transport.route("https://api.acoustid.org", lambda url, data: {"ok": True})
    http = client(transport, clock)

    http.post(
        "https://api.acoustid.org/v2/lookup",
        {"client": "a", "fp": "x"},
        secret=frozenset({"client"}),
    )
    http.post(
        "https://api.acoustid.org/v2/lookup",
        {"client": "b", "fp": "x"},
        secret=frozenset({"client"}),
    )

    assert len(transport.requests) == 1


def test_only_https() -> None:
    from djlib.enrich.http import UrllibTransport

    with pytest.raises(TransportError, match=r"only https"):
        UrllibTransport().request("GET", "file:///etc/passwd", None, {})
