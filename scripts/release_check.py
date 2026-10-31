"""Check that a release's version agrees everywhere, and print its release notes.

Usage: python scripts/release_check.py VERSION   (``0.1.0`` or the tag ``v0.1.0``)

The version must be the one in ``pyproject.toml`` and have a section in
``CHANGELOG.md``; that section, without its heading, is printed as the notes.
Exits with 1 and a message otherwise.
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseError(Exception):
    """The version does not agree with the package or the changelog."""


def release_notes(version: str, root: Path = ROOT) -> str:
    """The changelog section of ``version``, after checking it is the package's version."""
    version = version.removeprefix("v")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package = project["project"]["version"]
    if package != version:
        raise ReleaseError(f"version {version} does not match pyproject.toml ({package})")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.compile(rf"^## \[{re.escape(version)}\](?: - .*)?$", re.MULTILINE)
    found = heading.search(changelog)
    if found is None:
        raise ReleaseError(f"CHANGELOG.md has no section for {version}")
    end = re.compile(r"^(## |\[[^\]]+\]: )", re.MULTILINE).search(changelog, found.end())
    notes = changelog[found.end() : end.start() if end else len(changelog)].strip()
    if not notes:
        raise ReleaseError(f"the CHANGELOG.md section for {version} is empty")
    return notes + "\n"


def main(arguments: list[str]) -> None:
    if len(arguments) != 1:
        sys.exit(__doc__)
    try:
        sys.stdout.write(release_notes(arguments[0]))
    except ReleaseError as error:
        sys.exit(f"release check: {error}")


if __name__ == "__main__":
    main(sys.argv[1:])
