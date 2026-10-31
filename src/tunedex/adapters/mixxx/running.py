"""Whether Mixxx is running on this computer, as far as the process list tells.

Mixxx keeps its database open and writes to it when it quits, so writes are refused
while it runs. The check is best-effort: the hash check before writing remains the
real guard against a database that changed.
"""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

_TIMEOUT = 10


def mixxx_running() -> bool:
    if sys.platform.startswith("linux"):
        return _linux()
    if sys.platform == "darwin":
        return _command(["pgrep", "-x", "mixxx"], lambda out: bool(out.strip()))
    if sys.platform == "win32":
        return _command(
            ["tasklist", "/FI", "IMAGENAME eq mixxx.exe", "/NH"],
            lambda out: "mixxx.exe" in out.lower(),
        )
    return False


def _linux() -> bool:
    for comm in Path("/proc").glob("[0-9]*/comm"):
        try:
            if comm.read_text().strip() == "mixxx":
                return True
        except OSError:  # the process ended meanwhile, or is not ours to read
            continue
    return False


def _command(arguments: list[str], found: Callable[[str], bool]) -> bool:
    try:
        result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            arguments, capture_output=True, text=True, timeout=_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return found(result.stdout)
