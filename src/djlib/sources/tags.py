"""Reading track fields from audio files with mutagen (ID3, Vorbis comments, MP4 atoms)."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import mutagen
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4FreeForm
from mutagen.wave import WAVE

from djlib.model.key import Key, parse_musical, parse_open_key

# Fields a scan reads from files, in reporting order.
SCANNED_FIELDS = (
    "title",
    "artist",
    "album",
    "album_artist",
    "genre",
    "year",
    "track_number",
    "disc_number",
    "bpm",
    "key",
    "key_original",
    "composer",
    "remixer",
    "label",
    "comment",
    "grouping",
    "lyricist",
    "duration_us",
    "bitrate",
    "sample_rate",
    "file_format",
)

# field -> (ID3 frames, Vorbis comment names, MP4 atoms), in order of preference.
_SOURCES: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "title": (("TIT2",), ("TITLE",), ("\xa9nam",)),
    "artist": (("TPE1",), ("ARTIST",), ("\xa9ART",)),
    "album": (("TALB",), ("ALBUM",), ("\xa9alb",)),
    "album_artist": (("TPE2",), ("ALBUMARTIST",), ("aART",)),
    "genre": (("TCON",), ("GENRE",), ("\xa9gen",)),
    "year": (("TDRC",), ("DATE", "YEAR"), ("\xa9day",)),
    "track_number": (("TRCK",), ("TRACKNUMBER",), ("trkn",)),
    "disc_number": (("TPOS",), ("DISCNUMBER",), ("disk",)),
    "bpm": (("TBPM",), ("BPM",), ("tmpo",)),
    "key_original": (("TKEY",), ("INITIALKEY", "KEY"), ("----:com.apple.iTunes:initialkey",)),
    "composer": (("TCOM",), ("COMPOSER",), ("\xa9wrt",)),
    "remixer": (("TPE4",), ("REMIXER", "MIXARTIST"), ("----:com.apple.iTunes:REMIXER",)),
    "label": (("TPUB",), ("LABEL", "ORGANIZATION", "PUBLISHER"), ("----:com.apple.iTunes:LABEL",)),
    "comment": (("COMM",), ("COMMENT", "DESCRIPTION"), ("\xa9cmt",)),
    "grouping": (("TIT1", "GRP1"), ("GROUPING",), ("\xa9grp",)),
    "lyricist": (("TEXT",), ("LYRICIST",), ("----:com.apple.iTunes:LYRICIST",)),
}
_FORMATS: tuple[tuple[type, str], ...] = (
    (MP3, "mp3"),
    (FLAC, "flac"),
    (WAVE, "wav"),
    (AIFF, "aiff"),
    (MP4, "m4a"),
)
_EXTENSION_FORMATS = {".mp3": "mp3", ".flac": "flac", ".wav": "wav", ".aif": "aiff",
                      ".aiff": "aiff", ".m4a": "m4a", ".ogg": "ogg"}  # fmt: skip
# mutagen is only partially typed; opened files are handled dynamically.
_open_audio = cast("Callable[[Path], Any]", mutagen.File)  # pyright: ignore[reportUnknownMemberType]
_LEADING_NUMBER = re.compile(r"^\s*(\d+)")
_YEAR = re.compile(r"^\s*(\d{4})")


@dataclass
class FileFields:
    """Field values read from one file (only fields that were present) and warnings."""

    values: dict[str, Any] = field(default_factory=dict[str, Any])
    warnings: list[str] = field(default_factory=list[str])


def read_file(path: Path) -> FileFields:
    result = FileFields()
    try:
        audio = _open_audio(path)
    except Exception as error:  # mutagen raises many unrelated types for damaged files
        result.warnings.append(f"{path}: cannot read tags ({error})")
        audio = None
    if audio is None:
        if not result.warnings:
            result.warnings.append(f"{path}: not a recognizable audio file")
        result.values["file_format"] = _EXTENSION_FORMATS.get(path.suffix.lower())
        return result

    result.values["file_format"] = _format_of(audio, path)
    raw = _raw_values(audio)
    for name, texts in raw.items():
        _convert(name, texts, path, result)
    _audio_properties(audio, result)
    return result


def _format_of(audio: Any, path: Path) -> str | None:
    for cls, name in _FORMATS:
        if isinstance(audio, cls):
            return name
    return _EXTENSION_FORMATS.get(path.suffix.lower())


def _raw_values(audio: Any) -> dict[str, list[str]]:
    tags = audio.tags
    if tags is None:
        return {}
    if isinstance(tags, ID3):
        family, reader = 0, _id3_values
    elif isinstance(audio, MP4):
        family, reader = 2, _mp4_values
    else:
        family, reader = 1, _vorbis_values
    values: dict[str, list[str]] = {}
    for name, sources in _SOURCES.items():
        for key in sources[family]:
            texts = [t.strip() for t in reader(tags, key) if t and t.strip()]
            if texts:
                values[name] = texts
                break
    return values


def _id3_values(tags: Any, frame: str) -> list[str]:
    frames = tags.getall(frame)
    if frame == "COMM":
        return [str(text) for f in frames[:1] for text in f.text]
    return [str(text) for f in frames for text in f.text]


def _vorbis_values(tags: Any, name: str) -> list[str]:
    return [str(value) for value in tags.get(name, [])]


def _mp4_values(tags: Any, atom: str) -> list[str]:
    values: list[Any] = list(tags.get(atom, []))
    texts: list[str] = []
    for value in values:
        if isinstance(value, MP4FreeForm):
            texts.append(bytes(value).decode("utf-8", errors="replace"))
        elif isinstance(value, tuple):
            number = cast("tuple[Any, ...]", value)[0]  # (number, total) for trkn and disk
            texts.append(str(number))
        else:
            texts.append(str(value))
    return texts


def _convert(name: str, texts: list[str], path: Path, result: FileFields) -> None:
    text = "; ".join(texts)
    converters: dict[str, Callable[[str], Any]] = {
        "year": _year,
        "track_number": _leading_number,
        "disc_number": _leading_number,
        "bpm": _bpm,
    }
    converter = converters.get(name)
    if converter is None:
        result.values[name] = text
        if name == "key_original":
            result.values["key"] = _key(text)
        return
    value = converter(texts[0])
    if value is None:
        result.warnings.append(f"{path}: ignored invalid {name} {texts[0]!r}")
    else:
        result.values[name] = value


def _year(text: str) -> int | None:
    match = _YEAR.match(text)
    return int(match.group(1)) if match else None


def _leading_number(text: str) -> int | None:
    match = _LEADING_NUMBER.match(text)
    return int(match.group(1)) if match else None


def _bpm(text: str) -> float | None:
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    return value if 0 < value < 10_000 else None


def _key(text: str) -> Key | None:
    return parse_musical(text) or parse_open_key(text)


def _audio_properties(audio: Any, result: FileFields) -> None:
    info = audio.info
    length = getattr(info, "length", None)
    if isinstance(length, int | float) and length > 0:
        result.values["duration_us"] = round(length * 1_000_000)
    bitrate = getattr(info, "bitrate", None)
    if isinstance(bitrate, int | float) and bitrate > 0:
        result.values["bitrate"] = round(bitrate / 1000)
    sample_rate = getattr(info, "sample_rate", None)
    if isinstance(sample_rate, int) and sample_rate > 0:
        result.values["sample_rate"] = sample_rate
