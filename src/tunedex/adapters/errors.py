"""Errors raised by format adapters."""

from pathlib import Path


class AdapterError(Exception):
    """Base class for adapter failures."""


class AdapterReadError(AdapterError):
    """A file at the location cannot be read or decoded."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"cannot read {path}: {reason}")
        self.path = path


class UnknownAdapterError(AdapterError, LookupError):
    """No adapter has the requested name."""

    def __init__(self, name: str, available: list[str]) -> None:
        super().__init__(f"unknown adapter {name!r}; available: {', '.join(available)}")
        self.name = name
        self.available = available
