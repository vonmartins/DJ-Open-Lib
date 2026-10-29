"""Where beets keeps its library and music, from its environment and ``config.yaml``.

Only the top-level ``library`` and ``directory`` settings are read, with a minimal
parser, so that beets' YAML configuration needs no YAML dependency here.
"""

import os
import re
import sys
from pathlib import Path

from djlib.cli._flow import fail
from djlib.sources.beets import BeetsSource
from djlib.sources.beets.reader import database_path

_SETTING = re.compile(r"^(library|directory)\s*:\s*(.*?)\s*$")


def config_dir() -> Path:
    """beets' configuration directory: ``$BEETSDIR`` or the platform's default."""
    if beetsdir := os.environ.get("BEETSDIR"):
        return Path(beetsdir).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Roaming") / "beets"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    default = (Path(xdg) if xdg else Path.home() / ".config") / "beets"
    if sys.platform == "darwin" and not default.exists():
        legacy = Path.home() / "Library" / "Application Support" / "beets"
        if legacy.exists():
            return legacy
    return default


def config_settings(directory: Path) -> dict[str, str]:
    """The ``library`` and ``directory`` settings of ``config.yaml`` in ``directory``."""
    try:
        text = (directory / "config.yaml").read_text(encoding="utf-8")
    except OSError:
        return {}
    settings: dict[str, str] = {}
    for line in text.splitlines():
        match = _SETTING.match(line)  # top level only: indented lines never match
        if match is None:
            continue
        value = match.group(2)
        quote = value[:1]
        if quote in ("'", '"') and (end := value.find(quote, 1)) > 0:
            value = value[1:end]
        else:
            value = value.split(" #", 1)[0].strip()
        if value:
            settings[match.group(1)] = value
    return settings


def _setting_path(value: str, directory: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else directory / path


def default_beets_library() -> Path:
    directory = config_dir()
    library = config_settings(directory).get("library")
    return _setting_path(library, directory) if library else directory / "library.db"


def default_music_dir() -> Path:
    directory = config_dir()
    music = config_settings(directory).get("directory")
    return _setting_path(music, directory) if music else Path.home() / "Music"


def beets_library(source: BeetsSource, location: Path | None) -> Path:
    """The beets database at ``location`` or the default one; exits when there is none."""
    location = location or default_beets_library()
    detection = source.detect(location)
    if not detection.matches:
        fail(f"no beets library at {location}: {detection.reason}", "not_found")
    return database_path(location).absolute()
