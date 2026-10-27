"""Verified point-in-time copies of the files an operation is about to write.

Layout under the snapshot root::

    <root>/<target>/<seq>-<UTC timestamp>/manifest.json
    <root>/<target>/<seq>-<UTC timestamp>/files/0, files/1, ...

``manifest.json`` lists every file of the target in order; the copy of the n-th
file is ``files/<n>``. Files that did not exist are recorded as absent and have
no copy. Everything needed to list or restore a snapshot is in its directory,
so snapshots can also be inspected or restored by hand.

SQLite databases are copied with SQLite's backup mechanism. Close every store
that has a database open before restoring it.
"""

from djlib.snapshots.errors import RestoreError, SnapshotCorruptError, SnapshotError
from djlib.snapshots.manifest import FileRecord, Snapshot
from djlib.snapshots.snapshot_store import DEFAULT_KEEP, RestoreResult, SnapshotStore

__all__ = [
    "DEFAULT_KEEP",
    "FileRecord",
    "RestoreError",
    "RestoreResult",
    "Snapshot",
    "SnapshotCorruptError",
    "SnapshotError",
    "SnapshotStore",
]
