"""Schema migrations: numbered SQL files applied in order, one transaction each.

Rules for migration files (``schema/NNNN_description.sql``):

* Versions start at 1 and have no gaps.
* A file must not contain transaction statements (``BEGIN``, ``COMMIT``, ``ROLLBACK``);
  the runner wraps each migration in its own transaction.
* From the first public release on, files are append-only: never edit a released one.
"""

import re
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.resources import files

from djlib.store.errors import MigrationError

_FILE_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


def bundled_migrations() -> tuple[Migration, ...]:
    """The migrations shipped with the package, in version order."""
    migrations: list[Migration] = []
    for resource in (files("djlib.store") / "schema").iterdir():
        match = _FILE_NAME.match(resource.name)
        if match:
            migrations.append(
                Migration(int(match.group(1)), match.group(2), resource.read_text(encoding="utf-8"))
            )
    migrations.sort(key=lambda m: m.version)
    check_sequence(migrations)
    return tuple(migrations)


def check_sequence(migrations: Sequence[Migration]) -> None:
    versions = [m.version for m in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise ValueError(f"migration versions must be 1..n without gaps, got {versions}")


def schema_version(connection: sqlite3.Connection) -> int:
    (version,) = connection.execute("PRAGMA user_version").fetchone()
    return int(version)


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Sequence[Migration],
    *,
    before_first: Callable[[int], None] | None = None,
) -> list[int]:
    """Apply every migration newer than the database's version; return the versions applied.

    ``before_first`` is called with the current version just before the first pending
    migration runs (used to write a backup). If it raises, nothing is migrated.
    """
    check_sequence(migrations)
    current = schema_version(connection)
    pending = [m for m in migrations if m.version > current]
    if pending and before_first is not None:
        before_first(current)

    applied: list[int] = []
    for migration in pending:
        script = (
            f"BEGIN IMMEDIATE;\n{migration.sql}\n"
            f"PRAGMA user_version = {migration.version};\nCOMMIT;"
        )
        try:
            connection.executescript(script)
        except sqlite3.Error as error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise MigrationError(migration.version, error) from error
        applied.append(migration.version)
    return applied
