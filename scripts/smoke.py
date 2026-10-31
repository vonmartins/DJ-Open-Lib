"""Smoke test of an installed tunedex: the checks a built package must pass.

Usage: python scripts/smoke.py [COMMAND...]   (default: tunedex)

Runs ``--version`` and ``--help``, then applies a scan of a folder holding one test
clip to a new library in a temporary home, which needs the package's data files (the
schema migrations). Run it from a checkout of the repository. Exits with 1 on the
first failure.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CLIP = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "audio" / "silence.mp3"


def run(command: list[str], *arguments: str) -> str:
    result = subprocess.run(  # noqa: S603 - the command comes from the caller
        [*command, *arguments], capture_output=True, text=True, encoding="utf-8", check=False
    )
    if result.returncode != 0:
        sys.exit(
            f"smoke: {' '.join(arguments)} failed ({result.returncode})\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def main(command: list[str]) -> None:
    version = run(command, "--version").strip()
    if not version.startswith("tunedex "):
        sys.exit(f"smoke: unexpected version output {version!r}")
    help_text = run(command, "--help")
    for name in ("scan", "fix", "write-tags", "export", "snapshot"):
        if name not in help_text:
            sys.exit(f"smoke: {name} is missing from the help")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "music").mkdir()
        shutil.copyfile(CLIP, root / "music" / "clip.mp3")
        home = str(root / "home")
        run(command, "--home", home, "scan", str(root / "music"), "--apply", "--yes")
        status = json.loads(run(command, "--home", home, "status", "--json"))
        if not status["library_exists"] or status["tracks"] != 1:
            sys.exit(f"smoke: the scan did not create the library ({status})")
    print(f"smoke: {version} ok")


if __name__ == "__main__":
    main(sys.argv[1:] or ["tunedex"])
