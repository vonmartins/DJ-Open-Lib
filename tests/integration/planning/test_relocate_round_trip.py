"""A beets library made on another computer: import, relocate, then import and scan again."""

from pathlib import Path

from djlib.model.paths import normalize_path
from djlib.planning import Engine, assume_yes
from djlib.sources.beets import BeetsSource
from djlib.store import Store
from support.audio import tagged_copy
from support.beets import BeetsDatabase

BEETS = BeetsSource()


def test_relocated_tracks_stay_linked_and_scan_cleanly(
    engine: Engine, store: Store, tmp_path: Path
) -> None:
    music = tmp_path / "music"
    beets = BeetsDatabase(tmp_path / "beets" / "library.db")
    for artist, title in (("Calyx", "One"), ("Phace", "Two")):
        tagged_copy(music / artist, "mp3", name=f"{title}.mp3", title=title)
        beets.add_item(f"/mnt/server/music/{artist}/{title}.mp3", title=title, label="L")
    engine.apply(engine.plan_import(BEETS, beets.path), assume_yes)
    ids = {t.title: t.id for t in store.list_tracks()}

    relocation = engine.plan_relocate(music)
    engine.apply(relocation, assume_yes)

    assert len(relocation.tracks) == 2 and relocation.warnings == ()
    root = normalize_path(str(music))
    assert all(t.path.startswith(root + "/") for t in store.list_tracks())
    reimport = engine.plan_import(BEETS, beets.path)
    assert [t.change for t in reimport.tracks] == []
    scan = engine.plan_scan(music)
    assert [t.change for t in scan.tracks if t.change == "added"] == []
    engine.apply(scan, assume_yes)
    assert {t.title: t.id for t in store.list_tracks()} == ids
    assert all(store.file_state(track_id) is not None for track_id in ids.values())
    assert {t.label for t in store.list_tracks()} == {"L"}
