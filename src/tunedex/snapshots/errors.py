"""Errors raised by snapshots."""


class SnapshotError(Exception):
    """Base class for snapshot failures."""


class SnapshotCorruptError(SnapshotError):
    """A snapshot does not match its manifest; nothing was restored from it."""


class RestoreError(SnapshotError):
    """Restoring failed after it started changing files.

    ``rolled_back`` tells whether the target was put back to its pre-restore state.
    """

    def __init__(self, message: str, *, rolled_back: bool) -> None:
        super().__init__(message)
        self.rolled_back = rolled_back
