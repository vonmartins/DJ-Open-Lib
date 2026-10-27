import dataclasses

import pytest

from djlib.model.errors import ValidationError
from djlib.model.ids import new_track_id
from djlib.model.playlist import Folder, MatchMode, Playlist, Rule, Smartlist


def test_folder_with_tracks_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Folder(name="Sets", children=(new_track_id(),))  # pyright: ignore[reportArgumentType]
    assert (excinfo.value.entity, excinfo.value.field) == ("Folder", "children")


def test_playlist_has_no_children() -> None:
    assert not hasattr(Playlist(name="p"), "children")


def test_repeated_track_kept_in_order() -> None:
    a, b = new_track_id(), new_track_id()
    assert Playlist(name="Set", entries=(a, b, a)).entries == (a, b, a)


def test_entries_must_be_track_ids() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Playlist(name="Set", entries=("not-an-id",))  # pyright: ignore[reportArgumentType]
    assert excinfo.value.field == "entries"


def test_nested_tree() -> None:
    inner = Playlist(name="Warmup")
    year = Folder(name="2026", children=(inner,))
    tree = Folder(name="Gigs", children=(year, Smartlist(name="s")))

    assert tree.children[0] == year
    assert year.children == (inner,)


def test_lists_are_stored_as_tuples() -> None:
    folder = Folder(name="f", children=[Playlist(name="p")])  # pyright: ignore[reportArgumentType]
    assert isinstance(folder.children, tuple)


def test_rule_structure_kept() -> None:
    rule = Rule(field="genre", operator="contains", values=("Drum",))
    smartlist = Smartlist(name="DnB", match=MatchMode.ALL, rules=(rule,))

    assert smartlist.match is MatchMode.ALL
    assert smartlist.rules == (Rule(field="genre", operator="contains", values=("Drum",)),)


def test_match_mode_accepts_its_text_value() -> None:
    assert Smartlist(name="s", match="any").match is MatchMode.ANY  # pyright: ignore[reportArgumentType]


def test_invalid_match_mode() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Smartlist(name="s", match="some")  # pyright: ignore[reportArgumentType]
    assert (excinfo.value.entity, excinfo.value.field) == ("Smartlist", "match")


@pytest.mark.parametrize(("field", "operator"), [("", "contains"), ("genre", "")])
def test_rule_names_required(field: str, operator: str) -> None:
    with pytest.raises(ValidationError):
        Rule(field=field, operator=operator)


def test_rule_values_must_be_json() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Rule(field="genre", operator="is", values=(object(),))  # pyright: ignore[reportArgumentType]
    assert excinfo.value.field == "values"


def test_node_name_must_be_text() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Playlist(name=None)  # pyright: ignore[reportArgumentType]
    assert excinfo.value.field == "name"


def test_node_unmapped_kept() -> None:
    folder = Folder(name="f", unmapped={"rekordbox_xml": {"Type": "0"}})
    assert folder.unmapped == {"rekordbox_xml": {"Type": "0"}}


def test_node_identity_kept_on_rename() -> None:
    playlist = Playlist(name="old")
    assert dataclasses.replace(playlist, name="new").id == playlist.id
