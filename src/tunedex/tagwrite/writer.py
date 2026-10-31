"""Writing field values into a file's tags through a temporary copy that replaces it.

MP3 files, and the ID3 chunk of WAV and AIFF files, are written as ID3v2.3; FLAC files
as Vorbis comments. Only the given fields change: every other frame, comment and
picture stays. The copy's audio stream is checked against the original's before the
copy replaces the file.
"""

import os
import secrets
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from mutagen import id3
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.wave import WAVE

from tunedex.model.key import Key, parse_musical, parse_open_key
from tunedex.sources.frames import ID3, SOURCES, VORBIS, is_comment
from tunedex.sources.tags import format_of_extension
from tunedex.tagwrite.regions import WRITABLE_FORMATS, LayoutError, audio_region, audio_sha256

WRITTEN_FIELDS = (
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
    "composer",
    "remixer",
    "label",
    "comment",
    "grouping",
    "lyricist",
)
"""The fields written to files, in the order plans list them."""

# ID3 frames that ID3v2.3 cannot hold; saving as ID3v2.3 drops them.
V24_ONLY_FRAMES = frozenset(
    {"ASPI", "EQU2", "RVA2", "SEEK", "SIGN", "TDEN", "TDRL", "TDTG", "TMOO", "TPRO", "TSOA",
     "TSOP", "TSOT", "TSST"}
)  # fmt: skip

# mutagen is only partially typed; opened files are handled dynamically.
_Open = Callable[[Path], Any]
_OPENERS: dict[str, _Open] = {
    "mp3": cast("_Open", MP3),
    "flac": cast("_Open", FLAC),
    "wav": cast("_Open", WAVE),
    "aiff": cast("_Open", AIFF),
}


class TagWriteError(Exception):
    """A file's tags could not be written; the file is as it was."""


def text_of(name: str, value: Any, key_original: str | None = None) -> str | None:
    """The text a field value is written as, or ``None`` to remove the field.

    A key is written as ``key_original`` when that text denotes the same key, and in
    musical notation otherwise.
    """
    if value is None or value == "":
        return None
    if isinstance(value, Key):
        original = (key_original or "").strip()
        if original and (parse_musical(original) or parse_open_key(original)) == value:
            return original
        return value.musical()
    if name == "bpm" and isinstance(value, float | int):
        return f"{round(float(value), 2):g}"
    return str(value)


def v24_only_frames(path: Path) -> set[str]:
    """The frames of an MP3 file's ID3v2.4 tag that saving it as ID3v2.3 drops."""
    try:
        tags: Any = id3.ID3(path)
    except Exception:  # no tag, or a damaged one: nothing to lose
        return set()
    if tags.version < (2, 4, 0):
        return set()
    names: set[str] = {str(key).split(":", 1)[0] for key in tags}
    return names & V24_ONLY_FRAMES


def write_tags(path: Path, fields: Mapping[str, str | None]) -> None:
    """Write ``fields`` (field name -> text, ``None`` to remove) into the tags of ``path``."""
    fmt = format_of_extension(os.fspath(path))
    if fmt not in WRITABLE_FORMATS:
        raise TagWriteError(f"{path}: {fmt or 'these'} files are not written")
    unknown = set(fields) - set(WRITTEN_FIELDS)
    if unknown:
        raise ValueError(f"fields that are not written: {', '.join(sorted(unknown))}")
    temporary = path.with_name(f".{path.name}.tunedex-{secrets.token_hex(4)}.tmp")
    try:
        audio = audio_sha256(path, audio_region(path, fmt))
        shutil.copyfile(path, temporary)
        shutil.copymode(path, temporary)
        _write(temporary, fmt, fields)
        if audio_sha256(temporary, audio_region(temporary, fmt)) != audio:
            raise TagWriteError(f"{path}: writing the tags would change the audio; not written")
        with temporary.open("rb+") as file:
            os.fsync(file.fileno())
        temporary.replace(path)
    except LayoutError as error:
        raise TagWriteError(f"{path}: {error}") from error
    except OSError as error:
        raise TagWriteError(f"{path}: cannot write the tags ({error})") from error
    finally:
        temporary.unlink(missing_ok=True)


def _write(path: Path, fmt: str, fields: Mapping[str, str | None]) -> None:
    try:
        audio = _OPENERS[fmt](path)
        if audio.tags is None:
            audio.add_tags()
        tags: Any = audio.tags
        if fmt == "flac":
            _write_vorbis(tags, fields)
            audio.save()
        else:
            _write_id3(tags, fields)
            tags.update_to_v23()  # saving as v2.3 alone keeps v2.4 frames
            if fmt == "mp3":
                audio.save(v2_version=3, v1=1)  # ID3v1 is updated when there is one
            else:
                audio.save(v2_version=3)
    except (OSError, TagWriteError):
        raise
    except Exception as error:  # mutagen raises many unrelated types for damaged files
        raise TagWriteError(f"cannot write the tags ({error})") from error


def _source(name: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    return SOURCES["key_original" if name == "key" else name]


def _write_id3(tags: Any, fields: Mapping[str, str | None]) -> None:
    for name, text in fields.items():
        frames = _source(name)[ID3]
        if name == "comment":
            for frame in list(tags.getall("COMM")):
                if is_comment(frame.desc):
                    del tags[frame.HashKey]
            if text is not None:
                tags.add(id3.COMM(encoding=3, lang="eng", desc="", text=[text]))
            continue
        if text is None:
            for frame in frames:
                tags.delall(frame)
            continue
        frame = frames[0]
        if frame in ("TRCK", "TPOS"):
            current = tags.getall(frame)
            text = _with_total(str(current[0].text[0]) if current and current[0].text else "", text)
        tags.setall(frame, [getattr(id3, frame)(encoding=3, text=[text])])


def _write_vorbis(tags: Any, fields: Mapping[str, str | None]) -> None:
    for name, text in fields.items():
        names = _source(name)[VORBIS]
        if text is None:
            for comment in names:
                if comment in tags:
                    del tags[comment]
            continue
        if name in ("track_number", "disc_number"):
            current = list(tags.get(names[0], []))
            text = _with_total(str(current[0]) if current else "", text)
        tags[names[0]] = [text]


def _with_total(current: str, number: str) -> str:
    """``number``, keeping the total of a current ``n/total`` value."""
    _, slash, total = current.partition("/")
    return f"{number}/{total.strip()}" if slash and total.strip() else number
