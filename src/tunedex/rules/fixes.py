"""The metadata fixes bundled with tunedex.

Each fix is a pure function from a track and its options to the field values it would
change. Fixes are conservative: they act only on the shapes they are written for, and a
fix applied to its own result changes nothing. They run in the order of ``FIXES``.
"""

import dataclasses
import html
import posixpath
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from tunedex.model.track import TEXT_FIELDS, Track
from tunedex.rules.errors import RuleError

Changes = dict[str, Any]
FixFunction = Callable[[Track, Mapping[str, Any]], Changes]

# Text fields that hold names and titles (not paths, formats or key text).
NAME_FIELDS = tuple(f for f in TEXT_FIELDS if f not in ("file_format", "key_original"))


@dataclass(frozen=True, slots=True)
class Fix:
    name: str
    function: FixFunction
    fields: tuple[str, ...]
    """The fields it changes by default; the ``fields`` option may name others."""
    on: bool = True
    options: frozenset[str] = field(default_factory=frozenset[str])
    """Options besides ``fields``."""


# Helpers


def _clean_spaces(text: str) -> str:
    return re.sub(r" {2,}", " ", text).strip()


def _per_field(transform: Callable[[str], str]) -> FixFunction:
    """A fix that applies ``transform`` to each of its fields' text."""

    def run(track: Track, options: Mapping[str, Any]) -> Changes:
        changes: Changes = {}
        for name in options["fields"]:
            value = getattr(track, name)
            if isinstance(value, str):
                new = _settled(transform, value)
                if new != value:
                    changes[name] = new or None
        return changes

    return run


def _settled(transform: Callable[[str], str], value: str, rounds: int = 8) -> str:
    """``transform`` applied until the value stops changing, so a fix is idempotent."""
    for _ in range(rounds):
        new = transform(value)
        if new == value:
            break
        value = new
    return value


def _has_alnum(text: str) -> bool:
    return any(c.isalnum() for c in text)


# fix_encoding

_SUSPICIOUS = re.compile(r"[ÃÂâÐÑ][\u0080-¿Œ-™]")
_ENTITY = re.compile(r"&(?:#\d{1,6}|#x[0-9a-fA-F]{1,6}|[a-zA-Z]{2,8});")


def fix_encoding_text(text: str) -> str:
    """Decode HTML entities and repair UTF-8 that was read as Windows-1252 or Latin-1."""
    if _ENTITY.search(text):
        text = html.unescape(text)
    for _ in range(3):  # text encoded twice needs two rounds
        if not _SUSPICIOUS.search(text):
            break
        repaired = _repair(text)
        if repaired is None or len(_SUSPICIOUS.findall(repaired)) >= len(_SUSPICIOUS.findall(text)):
            break
        text = repaired
    return text


def _repair(text: str) -> str | None:
    # Odd spaces are tried as plain spaces too, as normalize_characters leaves them.
    spaced = "".join(" " if unicodedata.category(c) == "Zs" else c for c in text)
    for candidate in dict.fromkeys((text, spaced)):
        for codec in ("cp1252", "latin-1"):
            try:
                return candidate.encode(codec).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return None


# normalize_characters

_CJK = re.compile(
    "[\u1100-\u11ff\u3040-\u30ff\u3130-\u318f\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]"
)
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\ufeff"))


def _ascii(char: str) -> str:
    """A full-width ASCII form's ASCII character, and the ideographic space as a space."""
    if "\uff01" <= char <= "\uff5e":
        return chr(ord(char) - 0xFEE0)
    return " " if char == "\u3000" else char


def normalize_characters_text(text: str) -> str:
    """Full-width ASCII to ASCII (outside CJK text), odd spaces to spaces, spaces collapsed."""
    if not _CJK.search(text):
        text = "".join(_ascii(c) for c in text)
    text = text.translate(_INVISIBLE)
    text = "".join(" " if unicodedata.category(c) == "Zs" else c for c in text)
    return _clean_spaces(text)


# remove_urls

_TLDS = (
    "com|net|org|info|biz|io|fm|me|tv|cc|ru|de|uk|fr|es|it|nl|pl|us|ca|au|be|ch|at|se|no|dk"
    "|fi|jp|cn|br|mx|ar|xyz|online|site|club|top|pro|music|audio|link|live|to|ws|eu"
)
_URL = re.compile(r"\s*[\(\[]?\s*(?:https?://|www\.)[^\s\)\]]+\s*[\)\]]?")
_BRACKETED_DOMAIN = re.compile(
    r"\s*[\(\[]\s*(?:[\w-]+\.)+(?:" + _TLDS + r")(?:/[^\s\)\]]*)?\s*[\)\]]", re.IGNORECASE
)
_TRAILING_DOMAIN = re.compile(r"\s+(?:[A-Za-z0-9-]+\.)+(?:" + _TLDS + r")\s*$", re.IGNORECASE)
_EDGES = re.compile("^[\\s\\-\u2013\u2014_|:~]+|[\\s\\-\u2013\u2014_|:~]+$")
# A URL or a bare domain, with its path: the underscores in it are part of it.
_LINK = re.compile(
    r"(?:https?://|www\.)\S+|(?:[A-Za-z0-9-]+\.)+(?:" + _TLDS + r")\b(?:/\S*)?", re.IGNORECASE
)


def remove_urls_text(text: str) -> str:
    stripped = _BRACKETED_DOMAIN.sub(" ", _URL.sub(" ", text))
    stripped = _TRAILING_DOMAIN.sub(" ", stripped)
    if stripped == text:
        return text
    stripped = _clean_spaces(_EDGES.sub("", stripped))
    return stripped if _has_alnum(stripped) else text  # a value that is only a URL stays


# remove_video_ids

_VIDEO_ID = re.compile(r"\s*\[([A-Za-z0-9_-]{11})\]\s*$")
_WORDS = re.compile(r"^(?:[A-Z][a-z]+)+\d*$")


def remove_video_ids_text(text: str) -> str:
    match = _VIDEO_ID.search(text)
    if match is None:
        return text
    video = match.group(1)
    mixed = any(c.islower() for c in video) and any(c.isupper() for c in video)
    rest = text[: match.start()].rstrip()
    if not mixed or _WORDS.match(video) or not rest:  # catalogue numbers, ExtendedMix…
        return text
    return rest


# underscores_to_spaces


def underscores_to_spaces_text(text: str) -> str:
    if "_" not in text or " " in text or not _has_alnum(text.replace("_", "")):
        return text
    parts: list[str] = []
    start = 0
    for link in _LINK.finditer(text):  # underscores inside URLs and domains are kept
        parts.append(re.sub(r"_+", " ", text[start : link.start()]) + link.group())
        start = link.end()
    parts.append(re.sub(r"_+", " ", text[start:]))
    return _clean_spaces("".join(parts))


# remove_leading_number

_LEADING_NUMBER = re.compile("^(\\d{1,3})\\s*(?:[-\u2013.)]|\\s-)\\s+(?=[^\\W\\d_])")
_STORE_ID = re.compile(r"^\d{6,8}\s+(?=[^\W\d_])")  # Beatport and other stores' track ids


def remove_leading_number(track: Track, options: Mapping[str, Any]) -> Changes:
    title = track.title
    if not title:
        return {}
    store_id = _STORE_ID.match(title)
    if store_id is not None:
        return {"title": title[store_id.end() :]}
    match = _LEADING_NUMBER.match(title)
    if match is None:
        return {}
    number = match.group(1)
    padded = len(number) == 2 and number.startswith("0")
    if not padded and int(number) != track.track_number:
        return {}
    return {"title": title[match.end() :]}


# title_from_file_name

_NUMBERED = re.compile(r"\.\d+$")
ID3V1_LENGTH = 30
_YEAR = re.compile(r"\s*[\[\(]\d{4}[\]\)]$")


def title_from_file_name(track: Track, options: Mapping[str, Any]) -> Changes:
    parsed = _from_file_name(track.path)
    if parsed is None:
        return {}
    artist, title, stem = parsed
    if track.title and track.title.strip():
        return _untruncated(track.title, (title, stem))
    changes: Changes = {"title": title}
    if not (track.artist and track.artist.strip()) and _has_alnum(artist):
        changes["artist"] = artist
    return changes


def _from_file_name(path: str) -> tuple[str, str, str] | None:
    """(artist, title, whole name) from a file name, or ``None`` when it has no title."""
    stem = posixpath.splitext(posixpath.basename(path))[0]
    stem = _YEAR.sub("", _NUMBERED.sub("", stem)).strip()
    if re.search(r"(?:^|\s)-\s*$", stem) or re.match(r"^\s*-(?:\s|$)", stem):
        return None  # "Artist - " or "- " with nothing after: no usable title
    artist, sep, title = stem.partition(" - ")
    if not sep:
        artist, title = "", stem
    title = normalize_characters_text(title)
    if not _has_alnum(title):
        return None
    return normalize_characters_text(artist), title, normalize_characters_text(stem)


def _untruncated(title: str, candidates: Sequence[str]) -> Changes:
    """The file name's title for a title cut at ID3v1's 30 characters."""
    if len(title) != ID3V1_LENGTH:
        return {}
    cut = _loose(title)
    for candidate in candidates:
        longer = _loose(candidate)
        # A title that cleanups made 30 characters long is not cut: leave it.
        cleaned = _loose(_settled(remove_urls_text, _settled(remove_video_ids_text, candidate)))
        if len(longer) > len(cut) and longer.startswith(cut) and cleaned != cut:
            return {"title": candidate}
    return {}


def _loose(text: str) -> str:
    return _clean_spaces(text.replace("_", " ")).casefold()


# split_artist_title


def split_artist_title(track: Track, options: Mapping[str, Any]) -> Changes:
    if (track.artist and track.artist.strip()) or not track.title:
        return {}
    artist, sep, title = track.title.partition(" - ")
    artist, title = artist.strip(), title.strip()
    if not sep or artist[:1] in ("[", "(", "#"):  # "[BREAKS] Artist - Title" is left alone
        return {}
    if not _has_alnum(artist) or not _has_alnum(title):
        return {}
    stem = posixpath.splitext(posixpath.basename(track.path))[0]
    if not _loose(stem).startswith(_loose(artist) + " - "):  # the file name must agree
        return {}
    return {"artist": artist, "title": title}


# extract_featured

_FEAT_GROUP = re.compile(r"\s*[\(\[]\s*(?:feat\.?|ft\.|featuring)\s+([^\(\)\[\]]+?)\s*[\)\]]", re.I)
_FEAT_TAIL = re.compile(r"\s+(?:feat\.?|ft\.)\s+([^\(\)\[\]]+?)\s*$", re.I)


def extract_featured(track: Track, options: Mapping[str, Any]) -> Changes:
    title, artist = track.title, track.artist
    if not title or not artist:
        return {}
    match = _FEAT_GROUP.search(title) or _FEAT_TAIL.search(title)
    if match is None:
        return {}
    guests = match.group(1).strip()
    rest = _clean_spaces(title[: match.start()] + " " + title[match.end() :])
    if not _has_alnum(rest) or not _has_alnum(guests):
        return {}
    changes: Changes = {"title": rest}
    if guests.casefold() not in artist.casefold():
        joiner = " & " if re.search(r"\b(?:feat\.?|ft\.)\s", artist, re.I) else " feat. "
        changes["artist"] = f"{artist}{joiner}{guests}"
    return changes


# extract_remixer

_REMIX = re.compile(r"[\(\[]([^\(\)\[\]]+?)\s+(?:remix|rmx|re-?edit)\s*[\)\]]", re.I)
_NOT_NAMES = frozenset(
    {
        "original", "official", "club", "radio", "extended", "dub", "vip", "instrumental",
        "vocal", "dance", "album", "single", "edit", "special", "bootleg", "remastered",
        "main", "short", "long", "re", "alternate", "alt", "mix", "version", "12", "7",
        '12"', '7"', "the", "a", "new", "old",
    }
)  # fmt: skip


def extract_remixer(track: Track, options: Mapping[str, Any]) -> Changes:
    if track.remixer or not track.title:
        return {}
    matches = list(_REMIX.finditer(track.title))
    if not matches:
        return {}
    names = matches[-1].group(1).strip()
    words = {w.casefold().strip(".'\"") for w in names.split()}
    if not _has_alnum(names) or words <= _NOT_NAMES:
        return {}
    return {"remixer": names}


# remove_itunes_data

_ITUNES_DATA = re.compile(r"^\s*(?:[0-9A-Fa-f]{8}\s+){3,}[0-9A-Fa-f]{8}\s*$")


def remove_itunes_data_text(text: str) -> str:
    return "" if _ITUNES_DATA.match(text) else text


# fix_case

_SMALL = frozenset(
    {
        "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "nor", "of",
        "on", "or", "the", "to", "vs", "vs.", "with",
    }
)  # fmt: skip
_ROMAN = re.compile(r"^(?=[ivx])x{0,3}(?:ix|iv|v?i{0,3})$", re.I)


def _title_word(word: str, first: bool, keep: Mapping[str, str]) -> str:
    core = word.strip("()[]{}\"'.,!?:;")
    folded = core.casefold()
    if folded in keep:
        return word.replace(core, keep[folded])
    if any(c.isdigit() for c in core):
        return word
    if core and _ROMAN.match(core):
        return word.replace(core, core.upper())
    if not first and folded in _SMALL:
        return word.lower()
    return "-".join(_capitalize(part) for part in word.lower().split("-"))


def _capitalize(part: str) -> str:
    for index, char in enumerate(part):
        if char.isalpha():
            return part[:index] + char.upper() + part[index + 1 :]
    return part


def fix_case(track: Track, options: Mapping[str, Any]) -> Changes:
    keep = {str(k).casefold(): str(k) for k in options.get("keep", ())}
    changes: Changes = {}
    for name in options["fields"]:
        value = getattr(track, name)
        if not isinstance(value, str) or not any(c.isalpha() for c in value):
            continue
        if value not in (value.upper(), value.lower()):
            continue
        if not any(sum(c.isalpha() for c in w) > 3 for w in value.split()):
            continue
        words = value.split(" ")
        new = " ".join(_title_word(w, i == 0, keep) for i, w in enumerate(words))
        if new != value:
            changes[name] = new
    return changes


FIXES: tuple[Fix, ...] = (
    Fix("title_from_file_name", title_from_file_name, ("title", "artist")),
    Fix("fix_encoding", _per_field(fix_encoding_text), NAME_FIELDS),
    Fix("normalize_characters", _per_field(normalize_characters_text), NAME_FIELDS),
    Fix("remove_urls", _per_field(remove_urls_text), ("title", "artist", "album")),
    Fix("remove_video_ids", _per_field(remove_video_ids_text), ("title",)),
    Fix("underscores_to_spaces", _per_field(underscores_to_spaces_text), ("title", "album")),
    Fix("remove_leading_number", remove_leading_number, ("title",)),
    Fix("split_artist_title", split_artist_title, ("artist", "title")),
    Fix("extract_featured", extract_featured, ("title", "artist")),
    Fix("extract_remixer", extract_remixer, ("remixer",)),
    Fix("remove_itunes_data", _per_field(remove_itunes_data_text), ("comment",)),
    Fix("fix_case", fix_case, ("title", "album"), on=False, options=frozenset({"keep"})),
)
BY_NAME: dict[str, Fix] = {fix.name: fix for fix in FIXES}
# Fixes whose fields option is meaningful (the others read and write fixed fields).
_FIELD_FIXES = frozenset(
    {"fix_encoding", "normalize_characters", "remove_urls", "remove_video_ids",
     "underscores_to_spaces", "fix_case"}
)  # fmt: skip


def fix_options(fix: Fix, raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Checked options for ``fix``, with its default fields."""
    raw = dict(raw or {})
    allowed = set(fix.options)
    if fix.name in _FIELD_FIXES:
        allowed.add("fields")
    unknown = set(raw) - allowed
    if unknown:
        raise RuleError(f"{fix.name}: unknown options {', '.join(sorted(unknown))}")
    fields: Sequence[Any] = raw.get("fields", fix.fields)
    if not isinstance(fields, list | tuple) or not all(f in NAME_FIELDS for f in fields):
        raise RuleError(f"{fix.name}: fields must be a list of text fields")
    keep: object = raw.get("keep", [])
    if not isinstance(keep, list):
        raise RuleError(f"{fix.name}: keep must be a list of words")
    words = [str(k) for k in keep]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return {**raw, "fields": tuple(fields), "keep": tuple(words)}


def apply(fix: Fix, track: Track, options: Mapping[str, Any] | None = None) -> Changes:
    """What ``fix`` would change on ``track`` (only values that differ)."""
    checked = fix_options(fix, options) if options is None or "fields" not in options else options
    original = track
    total: Changes = {}
    for _ in range(8):  # a fix applied to its own result must change nothing
        changes = {k: v for k, v in fix.function(track, checked).items() if getattr(track, k) != v}
        if not changes:
            break
        total.update(changes)
        track = dataclasses.replace(track, **changes)
    return {k: v for k, v in total.items() if getattr(original, k) != v}


FixChange = tuple[str, Any, str]
"""(field, new value, name of the fix that set it)."""


def run_fixes(
    track: Track, fixes: Sequence[tuple[Fix, Mapping[str, Any]]], rounds: int = 5
) -> tuple[Track, list[FixChange]]:
    """Apply ``fixes`` in order, repeating the sequence until the track stops changing.

    One fix's result can be another's input (a URL removed leaves mojibake to repair),
    so the sequence runs to a fixed point: running it again on the result changes nothing.
    """
    applied: list[FixChange] = []
    for _ in range(rounds):
        changed = False
        for fix, options in fixes:
            changes = apply(fix, track, options)
            if changes:
                track = dataclasses.replace(track, **changes)
                applied.extend((name, value, fix.name) for name, value in changes.items())
                changed = True
        if not changed:
            break
    return track, applied
