import dataclasses
import re
from pathlib import Path

import pytest

from tunedex.adapters.contract import Capabilities
from tunedex.model.library import Library
from tunedex.model.playlist import Folder, Playlist
from tunedex.model.track import Track
from tunedex.planning.errors import UnknownPlaylistError
from tunedex.planning.selection import covered, fingerprints, modified, resolve_paths, target_name

CAPS = Capabilities(track_fields=frozenset({"title"}), folders=True)
A, B = Track(path_origin="/music/a.mp3", title="A"), Track(path_origin="/music/b.mp3", title="B")
PEAK = Playlist(name="Peak", entries=(A.id,))
WARM = Playlist(name="Warm", entries=(B.id,))
TECHNO = Folder(name="Techno", children=(PEAK,))
LIBRARY = Library.build([A, B], [TECHNO, WARM])


def test_resolve_paths() -> None:
    assert resolve_paths(LIBRARY, ["Techno/Peak"]) == {PEAK.id}
    assert resolve_paths(LIBRARY, ["Techno", "/Warm/"]) == {TECHNO.id, WARM.id}


def test_unknown_path_lists_close_matches() -> None:
    with pytest.raises(UnknownPlaylistError, match=re.escape("did you mean 'Techno/Peak'")):
        resolve_paths(LIBRARY, ["Techno/peak"])


def test_folder_covers_its_subtree() -> None:
    assert [p.node.id for p in covered(LIBRARY, frozenset({TECHNO.id}))] == [TECHNO.id, PEAK.id]
    assert len(covered(LIBRARY, None)) == 3


def test_target_name(tmp_path: Path) -> None:
    name = target_name("m3u", tmp_path)

    assert re.fullmatch(r"m3u-[0-9a-f]{12}", name)
    assert name == target_name("m3u", tmp_path / "x" / "..")  # normalized
    assert name != target_name("m3u", tmp_path / "other")


def test_unchanged_library_has_nothing_modified() -> None:
    assert modified(LIBRARY, CAPS, fingerprints(LIBRARY, CAPS)) == frozenset()


def test_never_exported_is_modified() -> None:
    assert modified(LIBRARY, CAPS, {}) == {TECHNO.id, PEAK.id, WARM.id}


def test_added_entry_modifies_only_that_playlist() -> None:
    recorded = fingerprints(LIBRARY, CAPS)
    grown = dataclasses.replace(WARM, entries=(B.id, A.id))
    library = Library.build([A, B], [TECHNO, grown])

    assert modified(library, CAPS, recorded) == {WARM.id}


def test_exported_track_field_modifies_its_playlists() -> None:
    recorded = fingerprints(LIBRARY, CAPS)
    retitled = Library.build([dataclasses.replace(A, title="A2"), B], [TECHNO, WARM])
    rebpm = Library.build([dataclasses.replace(A, bpm=128.0), B], [TECHNO, WARM])

    assert modified(retitled, CAPS, recorded) == {PEAK.id}
    assert modified(rebpm, CAPS, recorded) == frozenset()  # bpm is not exported


def test_reordered_folder_counts_as_changed() -> None:
    other = Playlist(name="Other")
    before = Library.build([A, B], [Folder(id=TECHNO.id, name="Techno", children=(PEAK, other))])
    after = Library.build([A, B], [Folder(id=TECHNO.id, name="Techno", children=(other, PEAK))])

    assert modified(after, CAPS, fingerprints(before, CAPS)) == {TECHNO.id}


def test_renamed_playlist_counts_as_changed() -> None:
    renamed = Library.build([A, B], [TECHNO, dataclasses.replace(WARM, name="Cool")])

    assert modified(renamed, CAPS, fingerprints(LIBRARY, CAPS)) == {WARM.id}
