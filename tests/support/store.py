from pathlib import Path

from tunedex.model.track import Track
from tunedex.store import Store
from tunedex.store.database import transaction
from tunedex.store.migrations import bundled_migrations


def old_database(path: Path, version: int, tracks: list[Track]) -> None:
    """Create a database at an older schema version holding ``tracks``.

    Write methods need the latest schema, so the rows are inserted directly.
    """
    with Store.open(path, migrations=bundled_migrations()[:version]) as store:
        db = store._db  # pyright: ignore[reportPrivateUsage]
        with transaction(db):
            store._insert_tracks(tracks)  # pyright: ignore[reportPrivateUsage]
