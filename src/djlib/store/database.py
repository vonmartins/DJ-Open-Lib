"""Opening djlib databases safely: identification, versioning, backups and transactions."""

import contextlib
import datetime
import sqlite3
from collections.abc import Generator, Sequence
from pathlib import Path

from djlib.store.errors import (
    BackupError,
    MigrationError,
    NotADjlibDatabaseError,
    SchemaTooNewError,
    StoreError,
)
from djlib.store.migrations import Migration, apply_migrations, bundled_migrations

APPLICATION_ID = 0x444A4C42  # ASCII "DJLB"
_SQLITE_HEADER = b"SQLite format 3\x00"


def open_database(path: Path, migrations: Sequence[Migration] | None = None) -> sqlite3.Connection:
    """Open (or create) the database at ``path`` and bring it to the latest schema.

    An existing file is inspected read-only first: files that are not djlib databases,
    or that come from a newer release, are refused without being written. Before
    migrating an existing file, a backup copy is written next to it.
    """
    migrations = bundled_migrations() if migrations is None else tuple(migrations)
    latest = migrations[-1].version if migrations else 0
    existed = path.exists()
    if existed:
        _inspect(path, latest)

    try:
        connection = sqlite3.connect(path, isolation_level=None)
    except sqlite3.Error as error:
        raise StoreError(f"cannot open {path}: {error}") from error
    try:
        connection.execute("PRAGMA foreign_keys = ON")

        def backup(version: int) -> None:
            _write_backup(connection, path, version)

        apply_migrations(connection, migrations, before_first=backup if existed else None)
    except BaseException as error:
        connection.close()
        if not existed and isinstance(error, MigrationError):
            path.unlink(missing_ok=True)
        raise
    return connection


@contextlib.contextmanager
def transaction(connection: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    """Run the block in one write transaction: all of it is committed, or none of it."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def _inspect(path: Path, latest: int) -> None:
    if not path.is_file():
        raise NotADjlibDatabaseError(path, "not a regular file")
    with path.open("rb") as file:
        if file.read(len(_SQLITE_HEADER)) != _SQLITE_HEADER:
            raise NotADjlibDatabaseError(path, "not an SQLite database")
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            (application_id,) = connection.execute("PRAGMA application_id").fetchone()
            (version,) = connection.execute("PRAGMA user_version").fetchone()
        finally:
            connection.close()
    except sqlite3.DatabaseError as error:
        raise NotADjlibDatabaseError(path, f"unreadable ({error})") from error
    if application_id != APPLICATION_ID:
        raise NotADjlibDatabaseError(path, "created by another application")
    if version > latest:
        raise SchemaTooNewError(path, version, latest)


def backup_path(path: Path, version: int) -> Path:
    """Name of the pre-migration copy: ``<name>.v<version>-<UTC timestamp>.bak``."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(f"{path.name}.v{version}-{stamp}.bak")
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.v{version}-{stamp}-{counter}.bak")
        counter += 1
    return candidate


def _write_backup(connection: sqlite3.Connection, path: Path, version: int) -> None:
    target = backup_path(path, version)
    temporary = target.with_name(target.name + ".tmp")
    try:
        copy = sqlite3.connect(temporary)
        try:
            connection.backup(copy)
        finally:
            copy.close()
        temporary.replace(target)
    except (OSError, sqlite3.Error) as error:
        temporary.unlink(missing_ok=True)
        raise BackupError(f"cannot write backup {target}: {error}") from error
