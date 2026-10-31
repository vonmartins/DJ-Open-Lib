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

from tunedex.model.key import Key, parse_musical, parse_open_key
from tunedex.sources.frames import ID3 as ID3_FRAMES
from tunedex.sources.frames import MP4 as MP4_ATOMS
from tunedex.sources.frames import SOURCES, VORBIS, is_comment

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

_FORMATS: tuple[tuple[type, str], ...] = (
    (MP3, "mp3"),
    (FLAC, "flac"),
    (WAVE, "wav"),
    (AIFF, "aiff"),
    (MP4, "m4a"),
)
_EXTENSION_FORMATS = {".mp3": "mp3", ".flac": "flac", ".wav": "wav", ".aif": "aiff",
                      ".aiff": "aiff", ".m4a": "m4a", ".ogg": "ogg"}  # fmt: skip


def format_of_extension(path: str) -> str | None:
    """The file format named after a path's extension, as scans name it."""
    suffix = path.rsplit("/", 1)[-1].rpartition(".")[2]
    return _EXTENSION_FORMATS.get(f".{suffix.lower()}") if suffix else None


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

    return read_audio(audio, path, result)


def read_audio(audio: Any, path: Path, result: FileFields | None = None) -> FileFields:
    """The field values of a file mutagen opened."""
    result = result or FileFields()
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
        family, reader = ID3_FRAMES, _id3_values
    elif isinstance(audio, MP4):
        family, reader = MP4_ATOMS, _mp4_values
    else:
        family, reader = VORBIS, _vorbis_values
    values: dict[str, list[str]] = {}
    for name, sources in SOURCES.items():
        for key in sources[family]:
            texts = [t.strip() for t in reader(tags, key) if t and t.strip()]
            if texts:
                values[name] = texts
                break
    return values


def _id3_values(tags: Any, frame: str) -> list[str]:
    frames = tags.getall(frame)
    if frame == "COMM":  # the first comment people wrote, not iTunes data
        comments = [f for f in frames if is_comment(f.desc)]
        return [str(text) for f in comments[:1] for text in f.text]
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
    elif value != 0:  # 0 means "not set" for numbers, years and BPM
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
    return value if 0 <= value < 10_000 else None


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
