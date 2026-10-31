import datetime
import hashlib
import json
from pathlib import Path

import pytest

from tunedex.adapters.contract import FileChange, Loss, WritePlan
from tunedex.adapters.m3u import M3UAdapter
from tunedex.model.cue import Cue, CueKind
from tunedex.model.key import Key, Mode
from tunedex.model.track import Track
from tunedex.planning.diff import added_fields
from tunedex.planning.model import (
    ApplyResult,
    ExportAction,
    FieldChange,
    FieldConflict,
    LibraryAction,
    NodeChange,
    Plan,
    TrackChange,
)
from tunedex.planning.render import (
    JSON_FORMAT,
    JSON_VERSION,
    bpm_text,
    json_value,
    render_text,
    text_value,
    to_json,
)
from tunedex.sources.scan_plan import MarkMissing

TRACK = Track(path_origin="/music/a.mp3", artist="Bicep", title="Glue")
A_MINOR = Key(tonic=9, mode=Mode.MINOR)


def updated(n: int) -> TrackChange:
    return TrackChange(
        change="updated",
        track_id=TRACK.id,
        path=f"/music/{n:03}.mp3",
        name=f"Track {n:03}",
        fields=(FieldChange("bpm", 126.0, 128.0),),
    )


def scan_plan(**fields: object) -> Plan:
    action = LibraryAction(operations=(MarkMissing(TRACK.id),), base_revision=3)
    return Plan(target="library", title="scan /music", action=action, **fields)  # pyright: ignore[reportArgumentType]


def test_mixed_plan_text() -> None:
    plan = scan_plan(
        tracks=(
            TrackChange(change="added", track_id=TRACK.id, path=TRACK.path, name="Bicep - Glue"),
            TrackChange(
                change="updated",
                track_id=TRACK.id,
                path="/music/b.mp3",
                name="B",
                fields=(
                    FieldChange("bpm", 126.0, 128.5),
                    FieldChange("key", None, A_MINOR),
                    FieldChange("title", "Old", "New"),
                    FieldChange("duration_us", 61_000_000, 125_400_000),
                    FieldChange("tags", (), ("Peak", "Dark")),
                ),
            ),
            TrackChange(
                change="moved",
                track_id=TRACK.id,
                path="/music/new/c.mp3",
                old_path="/music/c.mp3",
                name="C",
            ),
            TrackChange(change="missing", track_id=TRACK.id, path="/music/d.mp3", name="D"),
        ),
        refreshed=2,
        conflicts=(
            FieldConflict(
                track_id=TRACK.id,
                path="/music/b.mp3",
                name="B",
                field="genre",
                library_value="Techno",
                file_value="House",
            ),
        ),
        warnings=("/music/x.mp3: cannot read tags",),
    )

    assert render_text(plan) == (
        "scan /music\n"
        "Tracks: 1 added, 1 updated, 1 moved, 1 missing, 2 file states refreshed\n"
        "  + Bicep - Glue  /music/a.mp3\n"
        "  ~ B  /music/b.mp3\n"
        "      bpm: 126 → 128.5\n"
        "      key: — → 1m (Am)\n"
        "      title: 'Old' → 'New'\n"
        "      duration_us: 1:01 → 2:05\n"
        "      tags: — → Peak, Dark\n"
        "  > C  /music/c.mp3 → /music/new/c.mp3\n"
        "  ! D  /music/d.mp3\n"
        "Conflicts, library value kept: 1\n"
        "  B: genre is 'Techno' in the library, 'House' in the file\n"
        "Warnings: 1\n"
        "  /music/x.mp3: cannot read tags\n"
    )


def test_export_plan_text(tmp_path: Path) -> None:
    write_plan = WritePlan(
        adapter="m3u",
        location=tmp_path,
        changes=(
            FileChange(
                path=tmp_path / "Techno" / "Peak.m3u8",
                content=b"#EXTM3U\n",
                base_sha256=None,
                description="playlist Techno/Peak",
            ),
            FileChange(
                path=tmp_path / "Warm.m3u8",
                content=b"#EXTM3U\n",
                base_sha256="0" * 64,
                description="playlist Warm",
            ),
        ),
        losses=(
            Loss(kind="cues", description="cues are not supported", count=3, examples=("A", "B")),
        ),
    )
    plan = Plan(
        target="m3u-0123456789ab",
        title=f"export m3u to {tmp_path}",
        action=ExportAction(adapter=M3UAdapter(), write_plan=write_plan),
        nodes=(
            NodeChange(
                change="added", path=("Techno", "Peak"), kind="playlist", entries_added=("/a", "/b")
            ),
            NodeChange(
                change="updated",
                path=("Warm",),
                kind="playlist",
                entries_added=("/c",),
                entries_removed=("/a",),
                reordered=True,
            ),
        ),
        untouched_nodes=1,
        losses=write_plan.losses,
    )

    assert render_text(plan) == (
        f"export m3u to {tmp_path}\n"
        "Playlists: 1 added, 1 updated, 1 in the target but not in the library, left untouched\n"
        "  + Techno/Peak (playlist, 2 entries)\n"
        "  ~ Warm (playlist): 1 entries added, 1 removed, reordered\n"
        "Files: 1 to create, 1 to update\n"
        f"  create {tmp_path / 'Techno' / 'Peak.m3u8'}\n"
        f"  update {tmp_path / 'Warm.m3u8'}\n"
        "Losses: 1\n"
        "  - cues are not supported: 3 (e.g. A, B)\n"
    )
    assert to_json(plan)["files"] == [
        {"path": str(tmp_path / "Techno" / "Peak.m3u8"), "action": "create", "bytes": 8,
         "sha256_before": None, "sha256_after": hashlib.sha256(b"#EXTM3U\n").hexdigest(),
         "description": "playlist Techno/Peak"},
        {"path": str(tmp_path / "Warm.m3u8"), "action": "update", "bytes": 8,
         "sha256_before": "0" * 64, "sha256_after": hashlib.sha256(b"#EXTM3U\n").hexdigest(),
         "description": "playlist Warm"},
    ]  # fmt: skip


def test_empty_plan_text() -> None:
    plan = Plan(
        target="library", title="scan /music", action=LibraryAction(operations=(), base_revision=0)
    )

    assert render_text(plan) == "scan /music\nNothing to do.\n"
    assert to_json(plan)["empty"] is True


def test_human_text_is_bounded() -> None:
    plan = scan_plan(tracks=tuple(updated(n) for n in range(500)))

    text = render_text(plan, limit=20)

    assert "Track 019" in text
    assert "Track 020" not in text
    assert "  … and 480 more tracks\n" in text


def test_json_is_complete() -> None:
    plan = scan_plan(tracks=tuple(updated(n) for n in range(500)))

    document = json.loads(json.dumps(to_json(plan)))

    assert (document["format"], document["version"]) == (JSON_FORMAT, JSON_VERSION)
    assert len(document["tracks"]) == 500
    assert document["tracks"][499]["fields"] == [
        {"field": "bpm", "before": 126.0, "after": 128.0, "by": None}
    ]
    assert document["result"] is None


def test_json_result() -> None:
    result = ApplyResult(status="applied", snapshot="0001-x", operations_applied=1)

    assert to_json(scan_plan(), result)["result"] == {
        "status": "applied",
        "snapshot": "0001-x",
        "files_written": 0,
        "operations_applied": 1,
        "files_trashed": 0,
        "files_renamed": 0,
        "warnings": [],
    }


def test_json_values() -> None:
    cue = Cue(kind=CueKind.LOOP, start_us=0, end_us=10, slot=None)

    assert json_value(A_MINOR) == {"open_key": "1m", "musical": "Am"}
    assert json_value(datetime.date(2026, 10, 27)) == "2026-10-27"
    assert json_value(("a", "b")) == ["a", "b"]
    assert json_value((cue,)) == [
        {"kind": "loop", "start_us": 0, "slot": None, "name": None, "color": None,
         "end_us": 10, "active": False, "unmapped": {}}
    ]  # fmt: skip


def test_merge_base_only() -> None:
    plan = scan_plan(rebased=3)

    assert "Tracks: merge base updated for 3\n" in render_text(plan)
    assert to_json(plan)["rebased"] == 3


def test_added_track_fields_only_in_json() -> None:
    track = Track(path_origin="/music/new.mp3", title="New", bpm=128.0)
    change = TrackChange(
        change="added",
        track_id=track.id,
        path=track.path,
        name="New",
        fields=added_fields(track),
    )
    plan = scan_plan(tracks=(change,))

    assert "bpm" not in render_text(plan)
    (document,) = to_json(plan)["tracks"]  # type: ignore[misc]
    assert document["name"] == "New"  # type: ignore[index]
    assert document["fields"] == [  # type: ignore[index]
        {"field": "title", "before": None, "after": "New", "by": None},
        {"field": "bpm", "before": None, "after": 128.0, "by": None},
    ]


@pytest.mark.parametrize(
    ("bpm", "shown"), [(128.0, "128"), (127.5, "127.5"), (174.254, "174.25"), (99.999, "100")]
)
def test_bpm_text(bpm: float, shown: str) -> None:
    assert bpm_text(bpm) == shown
    assert text_value("bpm", bpm) == shown
