"""Chromaprint fingerprints, computed by the ``fpcalc`` program and cached per file."""

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from djlib.enrich.cache import Cache
from djlib.enrich.errors import EnrichError

INSTALL_HINT = (
    "fpcalc (Chromaprint) is needed to fingerprint tracks. Install it with your package"
    " manager (Arch: pacman -S chromaprint; Debian/Ubuntu: apt install"
    " libchromaprint-tools; macOS: brew install chromaprint) or download it from"
    " https://acoustid.org/chromaprint"
)
_LENGTH = 120  # seconds of audio, as AcoustID expects
_TIMEOUT = 120


@dataclass
class Fingerprinter:
    cache: Cache
    executable: str = "fpcalc"
    which: Callable[[str], str | None] = shutil.which
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    _program: str | None = field(default=None, init=False)

    def check(self) -> None:
        """Fail with install hints when ``fpcalc`` is not available."""
        if self._program is None:
            self._program = self.which(self.executable)
        if self._program is None:
            raise EnrichError(INSTALL_HINT)

    def fingerprint(self, path: Path) -> tuple[float, str]:
        """(duration in seconds, fingerprint) of the audio file at ``path``."""
        self.check()
        stat = path.stat()
        key = (os.fspath(path), stat.st_size, stat.st_mtime_ns)
        cached = self.cache.fingerprint(*key)
        if cached is not None:
            return cached
        try:
            result = self.run(
                [self._program, "-json", "-length", str(_LENGTH), os.fspath(path)],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise EnrichError(f"{path}: fpcalc failed ({error})") from error
        if result.returncode != 0:
            raise EnrichError(f"{path}: fpcalc failed ({result.stderr.strip()[:200]})")
        try:
            data = json.loads(result.stdout)
            duration, fingerprint = float(data["duration"]), str(data["fingerprint"])
        except (ValueError, KeyError, TypeError) as error:
            raise EnrichError(f"{path}: fpcalc gave an unexpected answer") from error
        self.cache.put_fingerprint(*key, duration, fingerprint)
        return duration, fingerprint
