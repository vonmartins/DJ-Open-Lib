"""No tracked file keeps the project's former working name."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Split so that this file does not match itself.
FORMER_NAME = "dj" + "lib"


def _tracked_files() -> list[Path]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("needs a git checkout")
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [ROOT / name for name in listing.decode().split("\0") if name]


def test_no_tracked_file_uses_the_former_name() -> None:
    offenders = []
    for path in _tracked_files():
        if FORMER_NAME in path.relative_to(ROOT).as_posix().lower():
            offenders.append(path.relative_to(ROOT).as_posix())
            continue
        if not path.is_file():
            continue
        content = path.read_bytes()
        if b"\0" in content:
            continue
        if FORMER_NAME in content.decode(errors="replace").lower():
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
