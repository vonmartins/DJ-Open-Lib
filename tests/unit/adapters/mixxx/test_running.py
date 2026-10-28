import subprocess
import sys

import pytest

from djlib.adapters.mixxx import running


def test_probe_answers() -> None:
    # CI machines never run Mixxx; on a desktop the answer depends on the user.
    assert isinstance(running.mixxx_running(), bool)


def test_failed_command_counts_as_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("pgrep", 10)

    monkeypatch.setattr(subprocess, "run", broken)
    assert running._command(["pgrep", "-x", "mixxx"], bool) is False  # pyright: ignore[reportPrivateUsage]


@pytest.mark.skipif(sys.platform != "win32", reason="tasklist output parsing")
def test_windows_probe() -> None:
    assert running.mixxx_running() in (True, False)
