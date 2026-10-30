"""File and folder arguments, read the same way by every command."""

from pathlib import Path

from djlib.cli._flow import fail


def folder(path: Path) -> Path:
    """``path`` with ``~`` expanded, made absolute; exits when it is not a folder."""
    expanded = path.expanduser()
    if not expanded.exists():
        fail(f"{path} does not exist", "not_found")
    if not expanded.is_dir():
        fail(f"{path} is not a directory")
    return expanded.absolute()


def optional_folder(path: Path | None) -> Path | None:
    return None if path is None else folder(path)


def file(path: Path) -> Path:
    """``path`` with ``~`` expanded, made absolute. Whether it exists is checked by its user."""
    return path.expanduser().absolute()


def optional_file(path: Path | None) -> Path | None:
    return None if path is None else file(path)
