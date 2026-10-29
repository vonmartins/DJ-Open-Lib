"""The names two tracks are compared by: artist and title without the usual noise.

Versions are part of the name: remixes, VIPs, edits and extended mixes are other songs.
"""

import re
import unicodedata

from djlib.model.track import Track
from djlib.rules.fixes import remove_urls_text, remove_video_ids_text

_FEAT = r"(?:feat\.?|ft\.?|featuring)"
_TITLE_GUEST_GROUP = re.compile(rf"\s*[\(\[]\s*{_FEAT}\s+([^\(\)\[\]]+?)\s*[\)\]]", re.I)
_TITLE_GUEST_TAIL = re.compile(rf"\s+{_FEAT}\s+([^\(\)\[\]]+?)\s*$", re.I)
_ARTIST_GUESTS = re.compile(rf"\s*[\(\[]?\s*\b{_FEAT}\s+(.+?)\s*[\)\]]?\s*$", re.I)
_GUEST_SEPARATORS = re.compile(r"\s*(?:,|&|\band\b|\bx\b)\s*", re.I)
_ORIGINAL = re.compile(r"\s*[\(\[]\s*original(?:\s+mix)?\s*[\)\]]", re.I)
_NOT_WORDS = re.compile(r"[\W_]+")


def normalize_text(text: str) -> str:
    """Compatibility forms folded, case ignored, punctuation and spaces collapsed."""
    folded = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold())
    return _NOT_WORDS.sub(" ", folded).strip()


def name_key(track: Track) -> tuple[str, str] | None:
    """The normalized artist and title, or ``None`` when either is missing."""
    if not track.title or not track.artist:
        return None
    title = remove_video_ids_text(remove_urls_text(track.title))
    guests: list[str] = []
    for pattern in (_TITLE_GUEST_GROUP, _TITLE_GUEST_TAIL):
        while (match := pattern.search(title)) is not None:
            guests.append(match.group(1))
            title = title[: match.start()] + " " + title[match.end() :]
    title = _ORIGINAL.sub(" ", title)
    artist = track.artist
    if (match := _ARTIST_GUESTS.search(artist)) is not None and match.start() > 0:
        guests.append(match.group(1))
        artist = artist[: match.start()]
    names = sorted(
        {
            name
            for guest in guests
            for part in _GUEST_SEPARATORS.split(guest)
            if (name := normalize_text(part))
        }
    )
    artist_key = normalize_text(artist)
    title_key = normalize_text(title)
    if not artist_key or not title_key:
        return None
    if names:
        artist_key = f"{artist_key} feat {' '.join(names)}"
    return artist_key, title_key
