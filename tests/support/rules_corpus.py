"""Table cases for the metadata fixes, read from ``tests/fixtures/rules``.

Each ``<fix>.yaml`` holds ``change`` rows (dirty values and what they become) and
``keep`` rows (clean values that look close to the fix's target and must not change).
A row is either the shorthand ``{in, out, why}`` on the file's ``field`` (``title`` by
default), or ``{track: {...}, expected: {...}, why}`` for several fields. ``clean.yaml``
lists clean values that no default fix may change.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from tunedex.model.track import Track

CORPUS = Path(__file__).parents[1] / "fixtures" / "rules"


@dataclass(frozen=True)
class Case:
    source: str
    """``file.yaml#n``, to find the row."""
    why: str
    track: Track
    expected: dict[str, Any] | None
    """Field values after the fix; ``None`` for a row that must not change."""
    options: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def id(self) -> str:
        return f"{self.source} {self.why}"


class CorpusError(ValueError):
    pass


def _track(values: dict[str, Any], source: str) -> Track:
    values = dict(values)
    path = values.pop("path", "/music/track.mp3")
    try:
        return Track(path_origin=path, **values)
    except (TypeError, ValueError) as error:
        raise CorpusError(f"{source}: {error}") from error


def _row(row: Any, name: str, index: int, kind: str, default_field: str) -> Case:
    source = f"{name}#{index} ({kind})"
    if not isinstance(row, dict):
        raise CorpusError(f"{source}: a row must be a mapping")
    why = row.get("why")
    if not isinstance(why, str) or not why:
        raise CorpusError(f"{source}: every row needs a why")
    options = row.get("options", {})
    if "in" in row:
        track = _track({default_field: row["in"]}, source)
        expected = None if kind == "keep" else {default_field: row.get("out")}
    elif "track" in row:
        track = _track(row["track"], source)
        expected = None if kind == "keep" else row.get("expected")
    else:
        raise CorpusError(f"{source}: a row needs `in` or `track`")
    if kind == "change" and not isinstance(expected, dict):
        raise CorpusError(f"{source}: a change row needs `out` or `expected`")
    return Case(source=source, why=why, track=track, expected=expected, options=options)


def load(fix: str, path: Path | None = None) -> list[Case]:
    """Every row of ``<fix>.yaml`` (or of ``path``)."""
    path = path or CORPUS / f"{fix}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("fix") != fix:
        raise CorpusError(f"{path.name}: must start with `fix: {fix}`")
    default_field = data.get("field", "title")
    options = data.get("options", {})
    cases: list[Case] = []
    for kind in ("change", "keep"):
        for index, row in enumerate(data.get(kind) or [], start=1):
            case = _row(row, path.name, index, kind, default_field)
            cases.append(Case(case.source, case.why, case.track, case.expected,
                              {**options, **case.options}))  # fmt: skip
    return cases


def clean() -> list[Track]:
    """The clean corpus: tracks that no default fix may change."""
    data = yaml.safe_load((CORPUS / "clean.yaml").read_text(encoding="utf-8"))
    tracks: list[Track] = []
    for group, rows in data.items():
        for index, row in enumerate(rows, start=1):
            tracks.append(_track(row, f"clean.yaml {group}#{index}"))
    return tracks
