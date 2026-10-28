"""Where Mixxx keeps its library, shared by ``import mixxx`` and ``export mixxx``."""

import os
import sys
from pathlib import Path

from djlib.adapters.mixxx import MixxxAdapter
from djlib.adapters.mixxx.reader import database_path
from djlib.cli._flow import fail


def default_mixxx_location() -> Path:
    """Mixxx's settings directory, which holds ``mixxxdb.sqlite``."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "Mixxx"
    if sys.platform == "darwin":
        sandboxed = (
            Path.home() / "Library" / "Containers" / "org.mixxx.mixxx" / "Data" / "Library"
            / "Application Support" / "Mixxx"
        )  # fmt: skip
        legacy = Path.home() / "Library" / "Application Support" / "Mixxx"
        return sandboxed if sandboxed.exists() or not legacy.exists() else legacy
    return Path.home() / ".mixxx"


def mixxx_database(adapter: MixxxAdapter, location: Path | None) -> Path:
    """The ``mixxxdb.sqlite`` at ``location`` or the default location; exits when there is none.

    Import and export always name the database file itself, so both see the same source.
    """
    location = location or default_mixxx_location()
    detection = adapter.detect(location)
    if not detection.matches:
        fail(f"no Mixxx library at {location}: {detection.reason}")
    return database_path(location).absolute()
