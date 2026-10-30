"""Progress displays on standard error (specs/cli-presentation)."""

import io
from pathlib import Path

import pytest

from djlib.cli._progress import FolderProgress, StepProgress


def captured(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Standard error swapped inside the test; pytest swaps its own in after fixtures run."""
    stream = io.StringIO()
    monkeypatch.setattr("sys.stderr", stream)
    return stream


def test_folder_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = captured(monkeypatch)
    progress = FolderProgress()

    progress(Path("/music"), 250)
    progress(Path("/music"), 312)
    progress.clear()

    assert "Searching: 312 files  /music" in stderr.getvalue()
    assert stderr.getvalue().endswith("\x1b[2K")  # erased
    progress.clear()  # a second clear does nothing


def test_enrich_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = captured(monkeypatch)
    progress = StepProgress()

    progress(3, 40)
    progress.clear()

    assert "3/40 tracks" in stderr.getvalue()
    assert stderr.getvalue().endswith("\x1b[2K")


def test_nothing_shown_before_the_first_report(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = captured(monkeypatch)
    FolderProgress().clear()

    assert stderr.getvalue() == ""
