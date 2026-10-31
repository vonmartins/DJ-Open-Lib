"""MusicBrainz data as track fields: the recording's identity and a chosen release."""

import datetime
from dataclasses import dataclass, field
from typing import Any

from tunedex.enrich.musicbrainz import Recording, Release, ReleaseRef
from tunedex.model.track import Track
from tunedex.model.unmapped import JSONValue
from tunedex.rules.fixes import extract_remixer

# Fields enrichment normalizes even when they have a value.
NORMALIZED = (
    "title",
    "artist",
    "remixer",
    "album",
    "album_artist",
    "year",
    "release_date",
    "label",
    "track_number",
    "disc_number",
)


@dataclass(frozen=True, slots=True)
class Mapped:
    fields: dict[str, Any]
    """Values for ``NORMALIZED`` fields that MusicBrainz has."""
    genre: str | None
    """Only to fill an empty genre."""
    unmapped: dict[str, JSONValue] = field(default_factory=dict[str, JSONValue])


def choose_release(recording: Recording, album: str | None) -> ReleaseRef | None:
    """The official release with the track's album title, else the earliest one."""
    official = [r for r in recording.releases if r.status == "Official"]
    if not official:
        return None
    if album:
        named = [r for r in official if r.title.casefold() == album.casefold()]
        if named:
            official = named
    return min(official, key=lambda r: (r.date or "9999", r.id))


def first_release_date(recording: Recording) -> str | None:
    dates = [r.date for r in recording.releases if r.status == "Official" and r.date]
    return min(dates) if dates else None


def map_recording(recording: Recording, release: Release | None, *, score: float) -> Mapped:
    values: dict[str, Any] = {}
    if recording.title:
        values["title"] = recording.title
    if recording.artist:
        values["artist"] = recording.artist
    remixers = ", ".join(recording.remixers)
    if not remixers and recording.title:
        # MusicBrainz often has no remixer relationship; the title names them.
        remixers = extract_remixer(Track(path_origin="/x", title=recording.title), {}).get(
            "remixer", ""
        )
    if remixers:
        values["remixer"] = remixers
    unmapped: dict[str, JSONValue] = {
        "recording_id": recording.id,
        "artist_ids": list(recording.artist_ids),
        "acoustid_score": round(score, 3),
    }
    if recording.isrcs:
        unmapped["isrcs"] = list(recording.isrcs)
    if release is not None:
        unmapped["release_id"] = release.id
        if release.title:
            values["album"] = release.title
        if release.artist:
            values["album_artist"] = release.artist
        if release.date:
            values["year"] = int(release.date[:4])
            if len(release.date) == 10:
                values["release_date"] = datetime.date.fromisoformat(release.date)
        if release.label:
            values["label"] = release.label
        if release.catalog_number:
            unmapped["catalog_number"] = release.catalog_number
        position = release.positions.get(recording.id)
        if position is not None:
            values["disc_number"], values["track_number"] = position
    genre = recording.genres[0][0].title() if recording.genres else None
    return Mapped(fields=values, genre=genre, unmapped=unmapped)
