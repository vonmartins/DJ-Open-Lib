"""Smoke tests for the installed ``tunedex`` command (specs/cli)."""

import re
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(sys.executable).parent
CONSOLE_SCRIPT = SCRIPTS_DIR / ("tunedex.exe" if sys.platform == "win32" else "tunedex")

INVOCATIONS = {
    "console-script": [str(CONSOLE_SCRIPT)],
    "module": [sys.executable, "-m", "tunedex"],
}

# CI runners force colored output, which splits words with ANSI escape codes.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8", cwd=cwd, check=False
    )
    result.stdout = ANSI_ESCAPE.sub("", result.stdout)
    result.stderr = ANSI_ESCAPE.sub("", result.stderr)
    return result


@pytest.fixture(params=sorted(INVOCATIONS))
def tunedex(request: pytest.FixtureRequest) -> list[str]:
    return INVOCATIONS[request.param]


def test_console_script_is_installed() -> None:
    assert CONSOLE_SCRIPT.is_file()


def test_version_matches_metadata(tunedex: list[str]) -> None:
    result = run([*tunedex, "--version"])

    assert result.returncode == 0
    assert result.stdout.strip() == f"tunedex {version('tunedex')}"


def test_module_and_console_script_report_same_version() -> None:
    outputs = {run([*argv, "--version"]).stdout for argv in INVOCATIONS.values()}

    assert len(outputs) == 1


def test_help_exits_zero(tunedex: list[str]) -> None:
    result = run([*tunedex, "--help"])

    assert result.returncode == 0
    assert "Usage" in result.stdout


def test_unknown_option_is_a_usage_error(tunedex: list[str]) -> None:
    result = run([*tunedex, "--no-such-option"])

    assert result.returncode != 0
    assert "--no-such-option" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("args", [["--version"], ["--help"], ["--no-such-option"]])
def test_invocation_creates_no_files(tunedex: list[str], args: list[str], tmp_path: Path) -> None:
    run([*tunedex, *args], cwd=tmp_path)

    assert list(tmp_path.iterdir()) == []
