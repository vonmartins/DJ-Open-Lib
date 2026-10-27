"""Mixxx beat grids: decoding its protobuf messages into canonical grids.

Mixxx stores ``BeatGrid-2.0`` (constant tempo) and ``BeatMap-1.0`` (one entry per beat)
messages; positions are in frames. Only the fields used here are decoded.
"""

import struct
from collections.abc import Iterator
from dataclasses import dataclass

from djlib.model.beatgrid import BeatGrid, BeatMarker

BEAT_GRID = "BeatGrid-2.0"
BEAT_MAP = "BeatMap-1.0"


class ProtobufError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _Field:
    number: int
    wire: int
    value: int | bytes


def _fields(data: bytes) -> Iterator[_Field]:
    """The fields of one protobuf message, in order (varint, 64-bit, bytes, 32-bit)."""
    position = 0
    while position < len(data):
        key, position = _varint(data, position)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, position = _varint(data, position)
            yield _Field(number, wire, value)
        elif wire == 1:
            yield _Field(number, wire, data[position : position + 8])
            position += 8
        elif wire == 2:
            length, position = _varint(data, position)
            yield _Field(number, wire, data[position : position + length])
            position += length
        elif wire == 5:
            yield _Field(number, wire, data[position : position + 4])
            position += 4
        else:
            raise ProtobufError(f"unsupported wire type {wire}")
        if position > len(data):
            raise ProtobufError("message is truncated")


def _varint(data: bytes, position: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if position >= len(data):
            raise ProtobufError("varint is truncated")
        byte = data[position]
        position += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, position
        shift += 7


def _int32(value: int | bytes) -> int:
    if not isinstance(value, int):
        raise ProtobufError("expected a varint")
    value &= (1 << 64) - 1
    return value - (1 << 64) if value >= 1 << 63 else value


def _message(value: int | bytes) -> bytes:
    if not isinstance(value, bytes):
        raise ProtobufError("expected a nested message")
    return value


def _beat(data: bytes) -> tuple[int, bool]:
    frame, enabled = 0, True
    for field in _fields(data):
        if field.number == 1:
            frame = _int32(field.value)
        elif field.number == 2:
            enabled = bool(_int32(field.value))
    return frame, enabled


def decode_grid(data: bytes) -> tuple[float, int]:
    """BPM and first-beat frame of a ``BeatGrid-2.0`` message."""
    bpm: float | None = None
    first = 0
    for field in _fields(data):
        if field.number == 1:
            for inner in _fields(_message(field.value)):
                if inner.number == 1 and inner.wire == 1 and isinstance(inner.value, bytes):
                    (bpm,) = struct.unpack("<d", inner.value)
        elif field.number == 2:
            first, _ = _beat(_message(field.value))
    if bpm is None:
        raise ProtobufError("the grid has no BPM")
    return bpm, first


def decode_map(data: bytes) -> list[int]:
    """Frames of the enabled beats of a ``BeatMap-1.0`` message."""
    frames: list[int] = []
    for field in _fields(data):
        if field.number == 1:
            frame, enabled = _beat(_message(field.value))
            if enabled:
                frames.append(frame)
    return sorted(frames)


def grid_from_mixxx(version: str, data: bytes, sample_rate: int) -> BeatGrid | None:
    """The canonical grid of a Mixxx beats blob; ``None`` for an empty beat map.

    Raises ``ProtobufError`` for damaged data and ``KeyError`` for unknown versions.
    """
    if version == BEAT_GRID:
        bpm, first = decode_grid(data)
        if bpm <= 0:
            return None
        interval = 60 * sample_rate / bpm
        index = 0
        while first + index * interval < 0:  # keep markers inside the track
            index += 1
        position = round((first + index * interval) / sample_rate * 1_000_000)
        return BeatGrid(markers=(BeatMarker(position_us=position, bpm=bpm, beat=index % 4 + 1),))
    if version == BEAT_MAP:
        return _grid_from_beats(decode_map(data), sample_rate)
    raise KeyError(version)


def _grid_from_beats(frames: list[int], sample_rate: int) -> BeatGrid | None:
    """One marker at the start of every run of equally spaced beats (within one frame).

    Each marker's BPM is the average over its run.
    """
    frames = sorted({f for f in frames if f >= 0})
    if len(frames) < 2:
        return None
    runs: list[tuple[int, int]] = []  # (first beat index, last beat index)
    spacing = frames[1] - frames[0]
    start = 0
    for index in range(1, len(frames) - 1):
        step = frames[index + 1] - frames[index]
        if abs(step - spacing) > 1:
            runs.append((start, index))
            start, spacing = index, step
    runs.append((start, len(frames) - 1))
    markers = tuple(
        BeatMarker(
            position_us=round(frames[first] / sample_rate * 1_000_000),
            bpm=60 * sample_rate * (last - first) / (frames[last] - frames[first]),
            beat=first % 4 + 1,
        )
        for first, last in runs
    )
    return BeatGrid(markers=markers)
