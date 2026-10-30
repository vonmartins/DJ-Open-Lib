import hashlib
from pathlib import Path

from support.adapter_contract import assert_plan_writes_nothing, write_plan_to_disk
from tunedex.adapters.contract import WriteOptions
from tunedex.adapters.m3u import M3UAdapter
from tunedex.adapters.pathmap import PathMapping, PathRule
from tunedex.model.library import Library
from tunedex.model.paths import normalize_path
from tunedex.model.playlist import Folder, Playlist, Smartlist
from tunedex.model.track import Track

FIXTURES = Path(__file__).parents[3] / "fixtures" / "m3u"
GLUE = Track(path_origin="/music/a.mp3", artist="Bicep", title="Glue", duration_us=372_400_000)


def single(playlist_name: str = "Set", *tracks: Track) -> Library:
    tracks = tracks or (GLUE,)
    return Library.build(
        tracks, [Playlist(name=playlist_name, entries=tuple(t.id for t in tracks))]
    )


def test_written_file(tmp_path: Path) -> None:
    plan = assert_plan_writes_nothing(M3UAdapter(), single(), tmp_path)

    (change,) = plan.changes
    assert change.path == tmp_path / "Set.m3u8"
    assert change.content == b"#EXTM3U\n#EXTINF:372,Bicep - Glue\n/music/a.mp3\n"
    assert change.action == "create" and change.base_sha256 is None
    assert "Set" in change.description


def test_display_fallbacks_and_repeats(tmp_path: Path) -> None:
    untitled = Track(path_origin="/music/Some File.mp3")
    titled = Track(path_origin="/music/b.mp3", title="Only\ntitle")
    library = Library.build(
        [untitled, titled], [Playlist(name="P", entries=(untitled.id, titled.id, untitled.id))]
    )

    (change,) = M3UAdapter().plan_write(library, tmp_path).changes

    assert change.content.decode().splitlines() == [
        "#EXTM3U",
        "#EXTINF:-1,Some File.mp3",
        "/music/Some File.mp3",
        "#EXTINF:-1,Only title",
        "/music/b.mp3",
        "#EXTINF:-1,Some File.mp3",
        "/music/Some File.mp3",
    ]


def test_mapped_windows_path(tmp_path: Path) -> None:
    track = Track(path_origin="/mnt/music/a.mp3")
    options = WriteOptions(path_mapping=PathMapping((PathRule("/mnt/music", "D:/Music"),)))

    (change,) = M3UAdapter().plan_write(single("Set", track), tmp_path, options).changes

    assert change.content.decode().splitlines()[-1] == "D:\\Music\\a.mp3"


def test_relative_option(tmp_path: Path) -> None:
    track = Track(path_origin=normalize_path(str(tmp_path / "music" / "a.mp3")))

    (change,) = (
        M3UAdapter(relative_paths=True).plan_write(single("Set", track), tmp_path / "lists").changes
    )

    expected = "../music/a.mp3" if str(tmp_path).startswith("/") else "..\\music\\a.mp3"
    assert change.content.decode().splitlines()[-1] == expected


def test_relative_option_falls_back_to_absolute(tmp_path: Path) -> None:
    track = Track(path_origin="Q:/Elsewhere/a.mp3")

    plan = M3UAdapter(relative_paths=True).plan_write(single("Set", track), tmp_path)

    assert plan.changes[0].content.decode().splitlines()[-1] == "Q:\\Elsewhere\\a.mp3"
    assert any("no relative path" in w for w in plan.warnings)


def test_nested_folders_written(tmp_path: Path) -> None:
    warmup = Playlist(name="Warmup", entries=(GLUE.id,))
    library = Library.build(
        [GLUE], [Folder(name="Gigs", children=(Folder(name="2026", children=(warmup,)),))]
    )

    plan = M3UAdapter().plan_write(library, tmp_path / "out")

    assert [c.path for c in plan.changes] == [tmp_path / "out" / "Gigs" / "2026" / "Warmup.m3u8"]


def test_invalid_characters_renamed_and_reported(tmp_path: Path) -> None:
    plan = M3UAdapter().plan_write(single("Drum & Bass: 170/174"), tmp_path)

    (change,) = plan.changes
    assert ":" not in change.path.name and "/" not in change.path.name
    (renamed,) = [loss for loss in plan.losses if loss.kind == "renamed"]
    assert renamed.examples == ("Drum & Bass: 170/174 → Drum & Bass_ 170_174",)


def test_colliding_names_get_suffixes(tmp_path: Path) -> None:
    library = Library.build(
        [GLUE], [Playlist(name="Set", entries=(GLUE.id,)), Playlist(name="set", entries=(GLUE.id,))]
    )
    names = [c.path.name for c in M3UAdapter().plan_write(library, tmp_path).changes]
    assert names == ["Set.m3u8", "set (2).m3u8"]


def test_selected_playlists(tmp_path: Path) -> None:
    a, b, c = (Playlist(name=n, entries=(GLUE.id,)) for n in "ABC")
    folder = Folder(name="F", children=(c,))
    library = Library.build([GLUE], [a, b, folder])

    only_a = M3UAdapter().plan_write(library, tmp_path, WriteOptions(selection=frozenset({a.id})))
    with_folder = M3UAdapter().plan_write(
        library, tmp_path, WriteOptions(selection=frozenset({folder.id}))
    )

    assert [ch.path.name for ch in only_a.changes] == ["A.m3u8"]
    assert [ch.path for ch in with_folder.changes] == [tmp_path / "F" / "C.m3u8"]


def test_base_hashes_and_unchanged_files(tmp_path: Path) -> None:
    other = Track(path_origin="/music/b.mp3")
    library = Library.build(
        [GLUE, other],
        [
            Playlist(name="Same", entries=(GLUE.id,)),
            Playlist(name="Changed", entries=(GLUE.id, other.id)),
            Playlist(name="New", entries=(other.id,)),
        ],
    )
    write_plan_to_disk(M3UAdapter().plan_write(library, tmp_path))
    (tmp_path / "Changed.m3u8").write_bytes(b"#EXTM3U\nold\n")
    (tmp_path / "New.m3u8").unlink()
    old_hash = hashlib.sha256(b"#EXTM3U\nold\n").hexdigest()

    plan = assert_plan_writes_nothing(M3UAdapter(), library, tmp_path)

    by_name = {c.path.name: c for c in plan.changes}
    assert set(by_name) == {"Changed.m3u8", "New.m3u8"}
    assert by_name["Changed.m3u8"].base_sha256 == old_hash
    assert by_name["New.m3u8"].base_sha256 is None


def test_plans_never_delete(tmp_path: Path) -> None:
    extra = tmp_path / "Old playlist.m3u8"
    extra.write_text("#EXTM3U\n/music/old.mp3\n", encoding="utf-8")

    plan = M3UAdapter().plan_write(single(), tmp_path)

    assert extra not in [c.path for c in plan.changes]
    assert extra.read_text(encoding="utf-8") == "#EXTM3U\n/music/old.mp3\n"


def test_directive_round_trip(tmp_path: Path) -> None:
    library = M3UAdapter().read(FIXTURES / "single" / "mixed.m3u8").library

    (change,) = M3UAdapter().plan_write(library, tmp_path).changes

    lines = change.content.decode().splitlines()
    assert lines.index("#EXTVLCOPT:start-time=5") == lines.index("/music/b.mp3") - 2


def test_changed_entry_drops_its_directive(tmp_path: Path) -> None:
    library = M3UAdapter().read(FIXTURES / "single" / "mixed.m3u8").library
    (playlist,) = library.playlists
    assert isinstance(playlist, Playlist)
    reordered = Library.build(
        library.tracks.values(),
        [
            Playlist(
                name=playlist.name,
                entries=tuple(reversed(playlist.entries)),
                unmapped=playlist.unmapped,
            )
        ],
    )

    plan = M3UAdapter().plan_write(reordered, tmp_path)

    assert b"EXTVLCOPT" not in plan.changes[0].content
    assert [loss.kind for loss in plan.losses if loss.kind == "directives-dropped"] == [
        "directives-dropped"
    ]


def test_smartlist_not_written(tmp_path: Path) -> None:
    library = Library.build(
        [GLUE], [Smartlist(name="Smart"), Playlist(name="P", entries=(GLUE.id,))]
    )

    plan = M3UAdapter().plan_write(library, tmp_path)

    assert [c.path.name for c in plan.changes] == ["P.m3u8"]
    (smart,) = [loss for loss in plan.losses if loss.kind == "smartlists"]
    assert smart.examples == ("Smart",)
