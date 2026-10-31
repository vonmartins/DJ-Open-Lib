from pathlib import Path

import pytest

from tunedex.snapshots import SnapshotError, SnapshotStore
from tunedex.snapshots.manifest import Rename, load_manifest
from tunedex.snapshots.moves import move_file


def renamed(app_dir: Path, snapshots: SnapshotStore) -> tuple[Path, list[Rename]]:
    """Two files renamed after a snapshot of the library file, as an applied rename leaves them."""
    library = app_dir / "library.txt"
    library.write_text("old paths", encoding="utf-8")
    renames = [
        Rename(old=str(app_dir / "a.mp3"), new=str(app_dir / "Artist - A.mp3")),
        Rename(old=str(app_dir / "b.mp3"), new=str(app_dir / "B.mp3")),
    ]
    for rename in renames:
        Path(rename.old).write_bytes(rename.old.encode())
    snapshot = snapshots.create("renames", [library], reason="rename", renames=renames)
    for rename in renames:
        move_file(Path(rename.old), Path(rename.new))
    library.write_text("new paths", encoding="utf-8")
    assert snapshot.renames == tuple(renames)
    return library, renames


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_restoring_renames_files_back_and_puts_back_the_library(
    snapshots: SnapshotStore, app_dir: Path
) -> None:
    library, renames = renamed(app_dir, snapshots)
    (snapshot,) = snapshots.list("renames")
    text = (snapshots.root / "renames" / snapshot.id / "manifest.json").read_text("utf-8")
    assert load_manifest(text) == snapshot

    result = snapshots.restore(snapshot)

    assert names(app_dir) == ["a.mp3", "b.mp3", "library.txt"]
    assert (app_dir / "a.mp3").read_bytes() == renames[0].old.encode()
    assert library.read_text(encoding="utf-8") == "old paths"

    snapshots.restore(result.pre_restore)  # and the restore can be undone
    assert names(app_dir) == ["Artist - A.mp3", "B.mp3", "library.txt"]
    assert library.read_text(encoding="utf-8") == "new paths"


def test_a_restore_is_refused_when_an_old_name_is_taken(
    snapshots: SnapshotStore, app_dir: Path
) -> None:
    library, _ = renamed(app_dir, snapshots)
    (app_dir / "a.mp3").write_bytes(b"someone else")
    (snapshot,) = snapshots.list("renames")

    with pytest.raises(SnapshotError, match=r"a\.mp3"):
        snapshots.restore(snapshot)

    assert names(app_dir) == ["Artist - A.mp3", "B.mp3", "a.mp3", "library.txt"]
    assert library.read_text(encoding="utf-8") == "new paths"


def test_a_restore_is_refused_when_a_file_is_gone(snapshots: SnapshotStore, app_dir: Path) -> None:
    renamed(app_dir, snapshots)
    (app_dir / "B.mp3").unlink()
    (snapshot,) = snapshots.list("renames")
    with pytest.raises(SnapshotError, match=r"B\.mp3 \(missing\)"):
        snapshots.restore(snapshot)
    assert (app_dir / "Artist - A.mp3").exists()


def test_a_case_only_rename(app_dir: Path) -> None:
    old = app_dir / "glue.mp3"
    old.write_bytes(b"x")
    move_file(old, app_dir / "Glue.mp3")
    assert names(app_dir) == ["Glue.mp3"]
    (app_dir / "other.mp3").write_bytes(b"y")
    with pytest.raises(FileExistsError):
        move_file(app_dir / "Glue.mp3", app_dir / "other.mp3")
