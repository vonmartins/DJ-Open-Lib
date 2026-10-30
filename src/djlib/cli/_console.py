"""Printing for people: color when it is wanted, and never a changed character."""

import colorsys
import contextvars
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Literal, TextIO

from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

# Kinds of text, named by meaning; only this module knows their colors.
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
    "secondary": "dim",
    "before": "red",
    "after": "green",
    "bpm": "cyan",
}
# Keys get a kind of their own, "key:6m", colored by their place on the key wheel.
_KEY_PREFIX = "key:"

# A piece of text and its kind; a line printed by echo_lines is one, by echo_rows several.
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
    # "auto" reads COLORTERM and TERM; a forced color with neither still gets 16 colors.
    made = _make(stream, "auto" if color else None, terminal=color or terminal)
    if color and made.color_system is None:
        made = _make(stream, "standard", terminal=True)
    return made


def _make(stream: TextIO, system: Literal["auto", "standard"] | None, *, terminal: bool) -> Console:
    return Console(
        file=stream,
        color_system=system,
        force_terminal=terminal,
        highlight=False,
        markup=False,
        emoji=False,
        soft_wrap=True,
    )


def echo(text: str, kind: str | None = None, *, err: bool = False) -> None:
    """Print one line in the style of ``kind``."""
    echo_rows([[(text, kind)]], err=err)


def echo_lines(lines: Iterable[Line], *, err: bool = False) -> None:
    """Print lines, each in the style of its kind, in one write."""
    echo_rows(([line] for line in lines), err=err)


def echo_spans(spans: Sequence[Line], *, err: bool = False) -> None:
    """Print one line made of pieces, each in the style of its kind."""
    echo_rows([spans], err=err)


def echo_rows(rows: Iterable[Sequence[Line]], *, err: bool = False) -> None:
    """Print lines made of pieces, each in the style of its kind, in one write."""
    out = console(err=err)
    wheel = out.color_system in ("256", "truecolor")
    text = Text()
    for row in rows:
        for content, kind in row:
            text.append(content, style=_style(kind or "", wheel=wheel))
        text.append("\n")
    out.print(text, end="")


def _style(kind: str, *, wheel: bool) -> str:
    if kind.startswith(_KEY_PREFIX):
        return key_style(kind.removeprefix(_KEY_PREFIX)) if wheel else ""
    return STYLES.get(kind, "")


def key_kind(open_key: str) -> str:
    """The kind of a key's text, such as ``key:6m``."""
    return _KEY_PREFIX + open_key


def key_style(open_key: str) -> str:
    """The key wheel's color for an Open Key: one hue per number, majors (``d``) lighter."""
    number, mode = int(open_key[:-1]), open_key[-1]
    lightness = 0.75 if mode == "d" else 0.62
    red, green, blue = colorsys.hls_to_rgb((number - 1) / 12, lightness, 0.75)
    return f"bold #{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"


def pad(text: str, width: int, *, right: bool = False) -> str:
    """``text`` padded to ``width`` screen cells; wide characters take two."""
    gap = " " * max(0, width - cell_len(text))
    return gap + text if right else text + gap


def cut(text: str, width: int) -> str:
    """``text`` cut to ``width`` screen cells, ending in an ellipsis when cut."""
    if cell_len(text) <= width:
        return text
    while cell_len(text) > width - 1:
        text = text[:-1]
    return text + "…"


def columns(rows: Sequence[Sequence[str]], indent: str = "") -> list[str]:
    """Rows as lines with each column padded to its widest cell (in screen cells).

    The last column is not padded.
    """
    if not rows:
        return []
    widths = [max(cell_len(row[i]) for row in rows) for i in range(len(rows[0]) - 1)]
    return [
        (
            indent + "  ".join([*(pad(c, w) for c, w in zip(row, widths, strict=False)), row[-1]])
        ).rstrip()
        for row in rows
    ]
