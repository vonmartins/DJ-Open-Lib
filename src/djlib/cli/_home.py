"""Where the library database and the snapshots live."""

import os
import sys
from pathlib import Path

DATABASE = "library.db"
SNAPSHOTS = "snapshots"


def default_home() -> Path:
    """The per-OS user data directory for djlib."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "djlib"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "djlib"
    base = os.environ.get("XDG_DATA_HOME", "")
    # The XDG spec says relative values are invalid and must be ignored.
    root = Path(base) if base and Path(base).is_absolute() else Path.home() / ".local" / "share"
    return root / "djlib"
