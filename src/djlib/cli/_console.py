"""Printing for people: color when it is wanted, and never a changed character."""

import contextvars
import os
import sys
from collections.abc import Iterable, Sequence
from typing import TextIO

from rich.console import Console
from rich.text import Text

# Kinds of line, named by meaning; only this module knows their colors.
STYLES = {
    "added": "green",
    "present": "green",
    "updated": "yellow",
    "moved": "cyan",
    "missing": "red",
    "removed": "red",
    "trash": "red",
    "merged": "magenta",
    "heading": "bold",
    "header": "bold",
    "folder": "bold",
    "chosen": "bold green",
    "warning": "yellow",
    "error": "bold red",
    "notice": "dim",
}

Line = tuple[str, str | None]

_no_color: contextvars.ContextVar[bool] = contextvars.ContextVar("no_color", default=False)


def set_no_color(value: bool) -> None:
    """Turn color off for the rest of the command (``--no-color``)."""
    _no_color.set(value)


def color_wanted(stream: TextIO) -> bool:
    """``--no-color`` and ``NO_COLOR`` win, then ``FORCE_COLOR``, then whether it is a terminal."""
    if _no_color.get() or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def console(*, err: bool = False, terminal: bool = False) -> Console:
    """A console on the current standard output or error; tests swap those streams.

    ``terminal`` treats the stream as a terminal even without color, for progress displays.
    """
    stream = sys.stderr if err else sys.stdout
    color = color_wanted(stream)
    return Console(
        file=stream,
        color_system="standard" if color else None,
        force_terminal=color or terminal,
        highlight=False,
        markup=False,
        emoji=False,
        soft_wrap=True,
    )


def echo(text: str, kind: str | None = None, *, err: bool = False) -> None:
    """Print one line in the style of ``kind``."""
    echo_lines([(text, kind)], err=err)


def echo_lines(lines: Iterable[Line], *, err: bool = False) -> None:
    """Print lines, each in the style of its kind, in one write."""
    text = Text()
    for content, kind in lines:
        text.append(content, style=STYLES.get(kind or "", ""))
        text.append("\n")
    console(err=err).print(text, end="")


def echo_spans(spans: Iterable[Line], *, err: bool = False) -> None:
    """Print one line made of parts, each in the style of its kind."""
    text = Text()
    for content, kind in spans:
        text.append(content, style=STYLES.get(kind or "", ""))
    text.append("\n")
    console(err=err).print(text, end="")


def columns(rows: Sequence[Sequence[str]], indent: str = "") -> list[str]:
    """Rows as lines with each column padded to its widest cell; the last one is not."""
    if not rows:
        return []
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]) - 1)]
    return [
        (
            indent + "  ".join([*(c.ljust(w) for c, w in zip(row, widths, strict=False)), row[-1]])
        ).rstrip()
        for row in rows
    ]
