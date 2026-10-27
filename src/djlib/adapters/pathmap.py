"""Rewriting path prefixes between the library and a target (for example another machine)."""

from collections.abc import Iterable
from dataclasses import dataclass

from djlib.model._validate import set_field
from djlib.model.paths import normalize_path


@dataclass(frozen=True, slots=True)
class PathRule:
    """Paths under ``library`` in the library are under ``target`` on the target."""

    library: str
    target: str

    def __post_init__(self) -> None:
        set_field(self, "library", normalize_path(self.library, entity="PathRule", field="library"))
        set_field(self, "target", normalize_path(self.target, entity="PathRule", field="target"))


@dataclass(frozen=True, slots=True)
class PathMapping:
    """Ordered prefix rules; the first rule whose prefix matches a path wins."""

    rules: tuple[PathRule, ...] = ()

    def __post_init__(self) -> None:
        set_field(self, "rules", tuple(self.rules))

    def to_target(self, path: str) -> str:
        """Library path to target path (normalized, ``/`` separators)."""
        return self._rewrite(path, ((r.library, r.target) for r in self.rules))

    def to_library(self, path: str) -> str:
        """Target path to library path (normalized, ``/`` separators)."""
        return self._rewrite(path, ((r.target, r.library) for r in self.rules))

    @staticmethod
    def _rewrite(path: str, pairs: Iterable[tuple[str, str]]) -> str:
        normalized = normalize_path(path)
        for source, destination in pairs:
            base = source.rstrip("/")
            if normalized == source or normalized.startswith(base + "/"):
                rest = normalized[len(base) :]
                return normalize_path(destination.rstrip("/") + rest if rest else destination)
        return normalized
