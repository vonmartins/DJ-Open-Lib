"""When the command line uses color (specs/cli-presentation)."""

import io
import re
from collections.abc import Iterator

import pytest

from djlib.cli import _console

ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    _console.set_no_color(False)
    yield
    _console.set_no_color(False)


def printed(stream: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("sys.stdout", stream)
    _console.echo_lines([("+ Rise [dOFq-swCWro]  /music/a.mp3", "added"), ("plain", None)])
    return stream.getvalue()


def test_terminal_gets_color(monkeypatch: pytest.MonkeyPatch) -> None:
    out = printed(Terminal(), monkeypatch)

    assert ESCAPE.search(out)
    assert ESCAPE.sub("", out) == "+ Rise [dOFq-swCWro]  /music/a.mp3\nplain\n"


def test_not_a_terminal_gets_none(monkeypatch: pytest.MonkeyPatch) -> None:
    assert printed(io.StringIO(), monkeypatch) == "+ Rise [dOFq-swCWro]  /music/a.mp3\nplain\n"


def test_force_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")

    assert ESCAPE.search(printed(io.StringIO(), monkeypatch))


@pytest.mark.parametrize("off", ["option", "environment"])
def test_no_color_wins_over_force_color(off: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    if off == "option":
        _console.set_no_color(True)
    else:
        monkeypatch.setenv("NO_COLOR", "1")

    out = printed(Terminal(), monkeypatch)

    assert "\x1b" not in out  # no color, and no bold or dim either
    assert out == "+ Rise [dOFq-swCWro]  /music/a.mp3\nplain\n"


def test_long_lines_are_not_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setattr("sys.stdout", stream := io.StringIO())
    line = "/music/" + "x" * 300 + ".mp3"

    _console.echo(line, "added")

    assert ESCAPE.sub("", stream.getvalue()) == line + "\n"


def test_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setattr("sys.stderr", stream := io.StringIO())

    _console.echo_spans([("error:", "error"), (" no such folder", None)], err=True)

    assert ESCAPE.sub("", stream.getvalue()) == "error: no such folder\n"


def test_columns() -> None:
    rows = [("library", "000002", "scan /music"), ("m3u:/out", "000001", "")]

    assert _console.columns(rows, indent="  ") == [
        "  library   000002  scan /music",
        "  m3u:/out  000001",
    ]
