import math
import shutil
import struct
import wave
from pathlib import Path

import pytest

from support.enrich import FakeFpcalc
from tunedex.enrich import EnrichError
from tunedex.enrich.cache import Cache
from tunedex.enrich.fingerprint import Fingerprinter


def test_fpcalc_missing(tmp_path: Path) -> None:
    printer = Fingerprinter(Cache(None), which=lambda _name: None)

    with pytest.raises(EnrichError, match=r"fpcalc .Chromaprint. is needed"):
        printer.check()


def test_cached_by_path_size_and_mtime(tmp_path: Path) -> None:
    track = tmp_path / "a.mp3"
    track.write_bytes(b"x")
    fpcalc = FakeFpcalc({"a.mp3": (200.5, "AQAAfp")})
    printer = Fingerprinter(Cache(None), which=lambda _name: "/usr/bin/fpcalc", run=fpcalc)

    assert printer.fingerprint(track) == (200.5, "AQAAfp")
    assert printer.fingerprint(track) == (200.5, "AQAAfp")
    assert len(fpcalc.calls) == 1

    track.write_bytes(b"changed")
    printer.fingerprint(track)
    assert len(fpcalc.calls) == 2


def test_fpcalc_failure(tmp_path: Path) -> None:
    track = tmp_path / "broken.mp3"
    track.write_bytes(b"x")
    printer = Fingerprinter(Cache(None), which=lambda _name: "fpcalc", run=FakeFpcalc())

    with pytest.raises(EnrichError, match=r"fpcalc failed"):
        printer.fingerprint(track)


def test_cache_persists(tmp_path: Path) -> None:
    track = tmp_path / "a.mp3"
    track.write_bytes(b"x")
    fpcalc = FakeFpcalc({"a.mp3": (10.0, "fp")})
    with Cache(tmp_path / "cache.db") as cache:
        Fingerprinter(cache, which=lambda _name: "fpcalc", run=fpcalc).fingerprint(track)
    with Cache(tmp_path / "cache.db") as cache:
        Fingerprinter(cache, which=lambda _name: "fpcalc", run=fpcalc).fingerprint(track)

    assert len(fpcalc.calls) == 1


def _tones(path: Path, seconds: int = 12) -> None:
    """A WAV of changing tones: silence gives Chromaprint nothing to fingerprint."""
    rate = 11025
    frames = bytearray()
    for i in range(rate * seconds):
        pitch = 220 * (1 + (i // (rate // 2)) % 5)
        frames += struct.pack("<h", int(12000 * math.sin(2 * math.pi * pitch * i / rate)))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(frames))


@pytest.mark.skipif(shutil.which("fpcalc") is None, reason="fpcalc is not installed")
def test_real_fpcalc(tmp_path: Path) -> None:
    clip = tmp_path / "tones.wav"
    _tones(clip)

    duration, fingerprint = Fingerprinter(Cache(None)).fingerprint(clip)

    assert round(duration) == 12 and len(fingerprint) > 20
