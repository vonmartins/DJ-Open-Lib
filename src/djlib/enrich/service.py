"""Everything enrichment talks to, bundled: fpcalc, AcoustID and MusicBrainz, cached."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from djlib.enrich import acoustid, musicbrainz
from djlib.enrich.acoustid import Lookup
from djlib.enrich.cache import Cache
from djlib.enrich.fingerprint import Fingerprinter
from djlib.enrich.http import Client, Transport, UrllibTransport
from djlib.enrich.musicbrainz import Recording, Release


@dataclass
class Services:
    fingerprinter: Fingerprinter
    client: Client
    _recordings: dict[str, Recording] = field(default_factory=dict[str, Recording])
    _releases: dict[str, Release] = field(default_factory=dict[str, Release])

    @classmethod
    def create(
        cls,
        cache: Cache,
        *,
        transport: Transport | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        run: Callable[..., object] | None = None,
        which: Callable[[str], str | None] | None = None,
    ) -> "Services":
        """The real services; tests replace the transport, clock and fpcalc."""
        client = Client(
            transport or UrllibTransport(),
            cache,
            intervals={musicbrainz.HOST: musicbrainz.INTERVAL, acoustid.HOST: acoustid.INTERVAL},
        )
        if clock is not None:
            client.clock = clock
        if sleep is not None:
            client.sleep = sleep
        fingerprinter = Fingerprinter(cache)
        if run is not None:
            fingerprinter.run = run  # pyright: ignore[reportAttributeAccessIssue]
        if which is not None:
            fingerprinter.which = which
        return cls(fingerprinter=fingerprinter, client=client)

    def check(self) -> None:
        self.fingerprinter.check()

    def fingerprint(self, path: Path) -> tuple[float, str]:
        return self.fingerprinter.fingerprint(path)

    def lookup(self, duration: float, fingerprint: str) -> Lookup:
        return acoustid.lookup(self.client, duration, fingerprint)

    def recording(self, recording_id: str) -> Recording:
        if recording_id not in self._recordings:
            self._recordings[recording_id] = musicbrainz.recording(self.client, recording_id)
        return self._recordings[recording_id]

    def release(self, release_id: str) -> Release:
        if release_id not in self._releases:
            self._releases[release_id] = musicbrainz.release(self.client, release_id)
        return self._releases[release_id]
