"""Writing files atomically: a reader sees either the old or the new content, never a mix."""

import contextlib
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

WriteFile = Callable[[Path, bytes], None]


def write_atomically(path: Path, content: bytes) -> None:
    """Replace ``path`` with ``content`` through a synced temporary file in its directory."""
    temporary = path.with_name(f".{path.name}.tunedex-{secrets.token_hex(4)}.tmp")
    try:
        with temporary.open("xb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix":  # Windows cannot open directories for syncing.
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass
class DirectoryTracker:
    """Creates missing parent directories and remembers them so they can be removed."""

    created: list[Path] = field(default_factory=list[Path])

    def ensure(self, directory: Path) -> None:
        missing: list[Path] = []
        current = directory
        while not current.exists():
            missing.append(current)
            current = current.parent
        for path in reversed(missing):
            path.mkdir()
            self.created.append(path)

    def remove_empty(self) -> None:
        """Remove the created directories that are empty, deepest first."""
        for path in sorted(self.created, key=lambda p: len(p.parts), reverse=True):
            with contextlib.suppress(OSError):
                path.rmdir()
