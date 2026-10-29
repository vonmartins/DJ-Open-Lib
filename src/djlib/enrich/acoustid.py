"""AcoustID: which MusicBrainz recordings a fingerprint belongs to."""

import os
from dataclasses import dataclass

from djlib.enrich.errors import EnrichError
from djlib.enrich.http import Client
from djlib.enrich.jsonish import obj, objects, text

LOOKUP = "https://api.acoustid.org/v2/lookup"
HOST = "api.acoustid.org"
INTERVAL = 0.34  # AcoustID allows 3 requests per second
# djlib's application key: it names the application, not a user (as beets and Picard
# ship theirs). DJLIB_ACOUSTID_KEY replaces it.
ACOUSTID_KEY = "CqO5K5QDz9"


def key() -> str:
    return os.environ.get("DJLIB_ACOUSTID_KEY") or ACOUSTID_KEY


@dataclass(frozen=True, slots=True)
class Candidate:
    recording_id: str
    score: float
    title: str | None
    artist: str | None
    duration: float | None
    """Seconds, as MusicBrainz knows the recording."""


@dataclass(frozen=True, slots=True)
class Lookup:
    best_score: float
    """The best match score, whether or not it links to recordings."""
    candidates: tuple[Candidate, ...]


def lookup(client: Client, duration: float, fingerprint: str) -> Lookup:
    answer = client.post(
        LOOKUP,
        {
            "client": key(),
            "duration": str(round(duration)),
            "fingerprint": fingerprint,
            "meta": "recordings",
            "format": "json",
        },
        secret=frozenset({"client"}),
    )
    return parse(answer)


def parse(value: object) -> Lookup:
    answer = obj(value)
    if answer.get("status") != "ok":
        message = text(obj(answer.get("error")).get("message"))
        raise EnrichError(f"AcoustID refused the lookup: {message or 'unknown error'}")
    best = 0.0
    seen: dict[str, Candidate] = {}
    for result in objects(answer.get("results")):
        score = float(result.get("score") or 0.0)
        best = max(best, score)
        for recording in objects(result.get("recordings")):
            recording_id = text(recording.get("id"))
            if recording_id is None:
                continue
            names = [n for a in objects(recording.get("artists")) if (n := text(a.get("name")))]
            duration = recording.get("duration")
            candidate = Candidate(
                recording_id=recording_id,
                score=score,
                title=text(recording.get("title")),
                artist=", ".join(names) or None,
                duration=float(duration) if isinstance(duration, int | float) else None,
            )
            previous = seen.get(recording_id)
            if previous is None or previous.score < score:
                seen[recording_id] = candidate
    ordered = sorted(seen.values(), key=lambda c: (-c.score, c.recording_id))
    return Lookup(best_score=best, candidates=tuple(ordered))
