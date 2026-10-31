"""Where the audio stream of a file is: every byte outside it belongs to its tags.

Regions are parsed from the bytes by tunedex, not taken from mutagen, so that tag
snapshots do not depend on how mutagen lays files out. Layouts that are not
understood are refused, never guessed.
"""

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

from tunedex.sources.tags import format_of_extension

WRITABLE_FORMATS = ("mp3", "flac", "wav", "aiff")
_CHUNK = 1024 * 1024
_ID3V1 = 128
_APE_FOOTER = 32
_MAX_PADDING = 64 * 1024


class LayoutError(Exception):
    """The file's layout is not one tunedex knows how to keep intact."""


@dataclass(frozen=True, slots=True)
class Region:
    """The audio stream is the bytes ``start`` to ``end`` of a file of ``size`` bytes."""

    start: int
    end: int
    size: int

    @property
    def tag_bytes(self) -> int:
        """How many bytes of the file are outside the audio stream."""
        return self.start + self.size - self.end


def audio_region(path: Path, fmt: str | None = None) -> Region:
    """The audio stream of ``path``, a file in format ``fmt`` or the one its extension names."""
    fmt = fmt or format_of_extension(os.fspath(path))
    parsers = {"mp3": _mp3, "flac": _flac, "wav": _wav, "aiff": _aiff}
    if fmt not in parsers:
        raise LayoutError(f"{path}: {fmt or 'this'} files are not supported")
    with path.open("rb") as file:
        size = os.fstat(file.fileno()).st_size
        start, end = parsers[fmt](file, size)
    if not 0 <= start < end <= size:
        raise LayoutError(f"{path}: no audio found")
    return Region(start, end, size)


def audio_sha256(path: Path, region: Region) -> str:
    """SHA-256 of the audio stream of ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        copy_range(file, region.start, region.end, digest.update)
    return digest.hexdigest()


def copy_range(file: BinaryIO, start: int, end: int, write: Callable[[bytes], object]) -> None:
    """Pass the bytes ``start`` to ``end`` of ``file`` to ``write``, in pieces."""
    file.seek(start)
    left = end - start
    while left > 0:
        piece = file.read(min(_CHUNK, left))
        if not piece:
            raise LayoutError("the file is shorter than expected")
        write(piece)
        left -= len(piece)


def _read_at(file: BinaryIO, offset: int, length: int) -> bytes:
    file.seek(offset)
    return file.read(length)


def _id3v2_end(file: BinaryIO, offset: int) -> int:
    """Where a leading ID3v2 tag at ``offset`` ends, or ``offset`` when there is none."""
    header = _read_at(file, offset, 10)
    if header[:3] != b"ID3":
        return offset
    if len(header) < 10:
        raise LayoutError("the ID3v2 tag header is damaged")
    major, flags, size = header[3], header[5], header[6:10]
    if major not in (2, 3, 4) or any(byte & 0x80 for byte in size):
        raise LayoutError("the ID3v2 tag header is damaged")
    length = _syncsafe(size)
    footer = 10 if major == 4 and flags & 0x10 else 0
    return offset + 10 + length + footer


def _syncsafe(data: bytes) -> int:
    value = 0
    for byte in data:
        value = (value << 7) | byte
    return value


def _skip_padding(file: BinaryIO, offset: int, size: int) -> int:
    """Skip zero bytes some taggers leave after a tag without counting them in it."""
    data = _read_at(file, offset, min(_MAX_PADDING, size - offset))
    return offset + len(data) - len(data.lstrip(b"\x00"))


def _trailing_tags(file: BinaryIO, start: int, size: int) -> int:
    """Where the audio ends: before the APEv2, Lyrics3v2 and ID3v1 tags at the end, in any order."""
    end = size
    id3v1 = False
    while True:
        if not id3v1 and end - _ID3V1 >= start and _read_at(file, end - _ID3V1, 3) == b"TAG":
            end -= _ID3V1
            id3v1 = True
            continue
        if end - _APE_FOOTER >= start and _read_at(file, end - _APE_FOOTER, 8) == b"APETAGEX":
            footer = _read_at(file, end - _APE_FOOTER, _APE_FOOTER)
            length = int.from_bytes(footer[12:16], "little")
            flags = int.from_bytes(footer[20:24], "little")
            end -= length + (_APE_FOOTER if flags & 0x80000000 else 0)
            continue
        if end - 15 >= start and _read_at(file, end - 9, 9) == b"LYRICS200":
            digits = _read_at(file, end - 15, 6)
            if not digits.isdigit():
                raise LayoutError("the Lyrics3 tag is damaged")
            end -= int(digits) + 15
            if end < start or _read_at(file, end, 11) != b"LYRICSBEGIN":
                raise LayoutError("the Lyrics3 tag is damaged")
            continue
        if end - 9 >= start and _read_at(file, end - 9, 9) == b"LYRICSEND":
            raise LayoutError("Lyrics3 version 1 tags are not supported")
        return end


def _mp3(file: BinaryIO, size: int) -> tuple[int, int]:
    start = _skip_padding(file, _id3v2_end(file, 0), size)
    sync = _read_at(file, start, 2)
    if len(sync) < 2 or sync[0] != 0xFF or sync[1] & 0xE0 != 0xE0:
        raise LayoutError("no MPEG audio frame where the audio should start")
    return start, _trailing_tags(file, start, size)


def _flac(file: BinaryIO, size: int) -> tuple[int, int]:
    position = _id3v2_end(file, 0)
    if _read_at(file, position, 4) != b"fLaC":
        raise LayoutError("no FLAC stream marker")
    position += 4
    while True:
        header = _read_at(file, position, 4)
        if len(header) < 4:
            raise LayoutError("the FLAC metadata is cut short")
        position += 4 + int.from_bytes(header[1:4])
        if header[0] & 0x80:
            break
    sync = _read_at(file, position, 2)
    if len(sync) < 2 or sync[0] != 0xFF or sync[1] & 0xFE != 0xF8:
        raise LayoutError("no FLAC audio frame after the metadata")
    end = size - _ID3V1 if _read_at(file, size - _ID3V1, 3) == b"TAG" else size
    return position, end


def _chunks(
    file: BinaryIO,
    size: int,
    *,
    order: Literal["little", "big"],
    forms: tuple[bytes, ...],
    audio: bytes,
) -> tuple[int, int]:
    header = _read_at(file, 0, 12)
    if len(header) < 12 or header[:4] != (b"RIFF" if order == "little" else b"FORM"):
        raise LayoutError("unknown container")
    if header[8:12] not in forms:
        raise LayoutError(f"unknown form {header[8:12]!r}")
    position = 12
    while position + 8 <= size:
        chunk = _read_at(file, position, 8)
        length = int.from_bytes(chunk[4:8], order)
        if chunk[:4] == audio:
            start = position + 8
            if start + length > size:
                raise LayoutError("the audio chunk is longer than the file")
            return start, start + length
        position += 8 + length + (length & 1)
    raise LayoutError("no audio chunk")


def _wav(file: BinaryIO, size: int) -> tuple[int, int]:
    return _chunks(file, size, order="little", forms=(b"WAVE",), audio=b"data")


def _aiff(file: BinaryIO, size: int) -> tuple[int, int]:
    return _chunks(file, size, order="big", forms=(b"AIFF", b"AIFC"), audio=b"SSND")
