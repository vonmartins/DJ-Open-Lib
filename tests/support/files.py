"""File helpers for tests."""

import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_bytes(location: Path) -> dict[str, bytes | None]:
    """Every file (bytes) and directory (``None``) under ``location``."""
    if not location.exists():
        return {}
    return {
        p.relative_to(location).as_posix(): (p.read_bytes() if p.is_file() else None)
        for p in sorted(location.rglob("*"))
    }
