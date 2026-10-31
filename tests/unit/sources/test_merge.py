from typing import Any

from tunedex.model.cue import Cue, CueKind
from tunedex.model.encoding import to_json
from tunedex.model.track import Track
from tunedex.sources.merge import FieldDisagreement, merge_fields

CUE = Cue(kind=CueKind.HOT, start_us=1_000, slot=0)
TRACK = Track(path_origin="/m/a.mp3", title="Glue", genre="Techno", bpm=None)
FIELDS = ("title", "genre", "bpm", "cues")


def encode(name: str, value: Any) -> Any:
    return to_json(value)


def base_of(**values: Any) -> dict[str, Any]:
    return {name: to_json(values.get(name)) for name in FIELDS}


def test_no_base_fills_only_empty_fields() -> None:
    theirs = {"title": "Glue (Edit)", "genre": "House", "bpm": 127.0, "cues": (CUE,)}

    changes, disagreements = merge_fields(TRACK, None, theirs, FIELDS, encode)

    assert changes == {"bpm": 127.0, "cues": (CUE,)}
    assert disagreements == []


def test_mine_unchanged_takes_theirs() -> None:
    base = base_of(title="Glue", genre="Techno", cues=())

    changes, _ = merge_fields(
        TRACK, base, {"title": "Glue", "genre": "Minimal", "cues": (CUE,)}, FIELDS, encode
    )

    assert changes == {"genre": "Minimal", "cues": (CUE,)}


def test_theirs_unchanged_keeps_mine() -> None:
    base = base_of(title="Old", genre="Techno")

    changes, disagreements = merge_fields(
        TRACK, base, {"title": "Old", "genre": "Techno"}, FIELDS, encode
    )

    assert changes == {}
    assert disagreements == []


def test_both_changed_is_a_disagreement() -> None:
    base = base_of(title="Glue", genre="Electro")

    changes, disagreements = merge_fields(
        TRACK, base, {"title": "Glue", "genre": "Minimal"}, FIELDS, encode
    )

    assert changes == {}
    assert disagreements == [FieldDisagreement("genre", "Techno", "Minimal")]


def test_both_changed_to_the_same_value_is_fine() -> None:
    base = base_of(title="Glue", genre="Electro")

    assert merge_fields(TRACK, base, {"title": "Glue", "genre": "Techno"}, FIELDS, encode) == (
        {},
        [],
    )


def test_removed_in_the_source() -> None:
    track = Track(path_origin="/m/a.mp3", cues=(CUE,))

    changes, _ = merge_fields(track, base_of(cues=(CUE,)), {"cues": ()}, ("cues",), encode)

    assert changes == {"cues": ()}
