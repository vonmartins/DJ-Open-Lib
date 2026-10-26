"""Errors raised by the library store."""

from pathlib import Path


class StoreError(Exception):
    """Base class for store failures."""


class NotADjlibDatabaseError(StoreError):
    """The file is not a djlib database; it was not modified."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path} is not a djlib database: {reason}")
        self.path = path


class SchemaTooNewError(StoreError):
    """The database was written by a newer release; it was not modified."""

    def __init__(self, path: Path, found: int, supported: int) -> None:
        super().__init__(
            f"{path} has schema version {found}, but this release supports up to {supported}"
        )
        self.path = path
        self.found = found
        self.supported = supported


class MigrationError(StoreError):
    """A migration failed; the database stays at the previous version."""

    def __init__(self, version: int, cause: Exception) -> None:
        super().__init__(f"migration to schema version {version} failed: {cause}")
        self.version = version


class BackupError(StoreError):
    """The pre-migration backup could not be written; nothing was migrated."""


class ConflictError(StoreError):
    """The operation would break a uniqueness rule (for example, a duplicate path)."""


class NotFoundError(StoreError):
    """The requested track or playlist node does not exist."""
