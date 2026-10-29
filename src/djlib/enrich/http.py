"""A small JSON client for web services: rate limits per host, retries and a cache.

Only ``djlib enrich`` uses it; nothing else in djlib makes network requests.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Any, Protocol

from djlib.enrich.cache import Cache
from djlib.enrich.errors import EnrichError

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_ATTEMPTS = 3
_TIMEOUT = 30


class TransportError(Exception):
    """The request did not get an answer (no network, timeout, refused connection)."""


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    body: bytes


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        data: Mapping[str, str] | None,
        headers: Mapping[str, str],
    ) -> Response: ...


class UrllibTransport:
    """The real network, through the standard library."""

    def request(
        self,
        method: str,
        url: str,
        data: Mapping[str, str] | None,
        headers: Mapping[str, str],
    ) -> Response:
        if not url.startswith("https://"):
            raise TransportError(f"only https URLs are requested, not {url!r}")
        body = None if data is None else urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as answer:  # noqa: S310
                return Response(answer.status, answer.read())
        except urllib.error.HTTPError as error:
            return Response(error.code, error.read())
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise TransportError(str(error)) from error


def user_agent() -> str:
    """How djlib names itself to services, as MusicBrainz requires."""
    return f"djlib/{version('djlib')} ( https://github.com/vonmartins/DJ-Open-Lib )"


@dataclass
class Client:
    """JSON requests with at least ``intervals[host]`` seconds between two to the same host."""

    transport: Transport
    cache: Cache
    intervals: Mapping[str, float] = field(default_factory=dict[str, float])
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    agent: str = field(default_factory=user_agent)
    _last: dict[str, float] = field(default_factory=dict[str, float])

    def get(self, url: str, params: Mapping[str, str]) -> Any:
        return self._json("GET", f"{url}?{urllib.parse.urlencode(sorted(params.items()))}", None)

    def post(
        self, url: str, data: Mapping[str, str], *, secret: frozenset[str] = frozenset()
    ) -> Any:
        """POST ``data``; fields in ``secret`` (an API key) are left out of the cache key."""
        key_data = {k: v for k, v in data.items() if k not in secret}
        return self._json("POST", url, data, cache_key=["POST", url, sorted(key_data.items())])

    def _json(
        self,
        method: str,
        url: str,
        data: Mapping[str, str] | None,
        *,
        cache_key: Any = None,
    ) -> Any:
        key = json.dumps(cache_key or [method, url], ensure_ascii=False)
        cached = self.cache.response(key)
        if cached is not None:
            return cached
        host = urllib.parse.urlsplit(url).hostname or ""
        headers = {"User-Agent": self.agent, "Accept": "application/json"}
        problem = ""
        for attempt in range(_ATTEMPTS):
            self._wait(host)
            try:
                response = self.transport.request(method, url, data, headers)
            except TransportError as error:
                problem = f"cannot reach {host} ({error})"
            else:
                if response.status == 200:
                    try:
                        value = json.loads(response.body)
                    except ValueError as error:
                        raise EnrichError(f"{host} sent an answer that is not JSON") from error
                    self.cache.put_response(key, value)
                    return value
                if response.status not in _RETRY_STATUSES:
                    text = response.body.decode("utf-8", "replace")[:200]
                    raise EnrichError(f"{host} answered {response.status}: {text}")
                problem = f"{host} answered {response.status}"
            if attempt + 1 < _ATTEMPTS:
                self.sleep(2**attempt)
        raise EnrichError(f"{problem}; try again later")

    def _wait(self, host: str) -> None:
        interval = self.intervals.get(host, 0.0)
        last = self._last.get(host)
        if last is not None:
            remaining = interval - (self.clock() - last)
            if remaining > 0:
                self.sleep(remaining)
        self._last[host] = self.clock()
