import datetime
import json

import pytest

from tunedex.snapshots.errors import SnapshotCorruptError
from tunedex.snapshots.manifest import FileRecord, Snapshot, dump_manifest, load_manifest

SNAPSHOT = Snapshot(
    id="000003-20261027T101500Z",
    target="traktor",
    created_at=datetime.datetime(2026, 10, 27, 10, 15, 0, 123456, tzinfo=datetime.UTC),
    tunedex_version="0.0.0",
    reason="pre-restore",
    files=(
        FileRecord(
            path="/a/collection.nml", present=True, size=12, sha256="ab" * 32, method="copy"
        ),
        FileRecord(path="/a/new.m3u", present=False),
    ),
)


def test_round_trip() -> None:
    assert load_manifest(dump_manifest(SNAPSHOT)) == SNAPSHOT


def test_manifest_fields() -> None:
    document = json.loads(dump_manifest(SNAPSHOT))

    assert document["manifest_version"] == 1
    assert document["created_at"] == "2026-10-27T10:15:00.123456Z"
    assert document["files"][1] == {"path": "/a/new.m3u", "present": False}


def test_sequence_from_id() -> None:
    assert SNAPSHOT.sequence == 3


def test_unknown_version_rejected() -> None:
    document = json.loads(dump_manifest(SNAPSHOT))
    document["manifest_version"] = 2

    with pytest.raises(SnapshotCorruptError, match="version"):
        load_manifest(json.dumps(document))


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "{}",
        json.dumps({"manifest_version": 1}),
        dump_manifest(SNAPSHOT).replace('"size": 12', '"size": -1'),
        dump_manifest(SNAPSHOT).replace('"method": "copy"', '"method": "zip"'),
        dump_manifest(SNAPSHOT).replace('"present": false', '"present": "no"'),
        dump_manifest(SNAPSHOT).replace("2026-10-27T10:15:00.123456Z", "yesterday"),
    ],
)
def test_malformed_manifest_rejected(text: str) -> None:
    with pytest.raises(SnapshotCorruptError):
        load_manifest(text)
