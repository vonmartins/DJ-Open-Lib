"""Names duplicates are compared by (specs/duplicates)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from djlib.duplicates.normalize import name_key, normalize_text
from djlib.model.track import Track


def key(artist: str | None, title: str | None) -> tuple[str, str] | None:
    return name_key(Track(path_origin="/music/a.mp3", artist=artist, title=title))


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (("Synkro", "Everyday (Original Mix) [OHvehxQLQ7E]"), ("synkro", "Everyday")),
        (("Synkro", "Everyday (Original)"), ("Synkro", "Everyday")),
        (("Glow Unit", "Rain (freebeats.com)"), ("Glow Unit", "Rain")),
        (("Glow Unit", "Rain  -  Part 2"), ("GLOW UNIT", "rain part 2")),
        (
            ("The Bug feat. Roger Robinson", "You and Me"),
            ("The Bug", "You and Me (feat. Roger Robinson)"),
        ),
        (("Echo Unit", "Storm ft. Mira & Sol"), ("Echo Unit feat. Sol, Mira", "Storm")),
        (
            ("\uff25\uff43\uff48\uff4f \uff35\uff4e\uff49\uff54", "\uff33\uff54\uff4f\uff52\uff4d"),
            ("Echo Unit", "Storm"),
        ),
        (("Café Noir", "Été"), ("Café Noir", "Été")),
    ],
)
def test_same_name(first: tuple[str, str], second: tuple[str, str]) -> None:
    assert key(*first) == key(*second)
    assert key(*first) is not None


@pytest.mark.parametrize(
    "version",
    [
        "Afterlife (Kryptic Minds Remix)",
        "Afterlife (VIP)",
        "Afterlife (Edit)",
        "Afterlife (Extended Mix)",
        "Afterlife (Radio Edit)",
        "Afterlife (Dub)",
        "Afterlife (Instrumental)",
        "Afterlife - Kryptic Minds Remix",
    ],
)
def test_versions_kept_apart(version: str) -> None:
    assert key("Lung", version) != key("Lung", "Afterlife")


def test_accents_are_not_ignored() -> None:
    assert key("Café Noir", "Été") != key("Cafe Noir", "Ete")


@pytest.mark.parametrize(
    ("artist", "title"), [(None, "Intro"), ("", "Intro"), ("Lung", None), ("Lung", "!!")]
)
def test_no_key(artist: str | None, title: str | None) -> None:
    assert key(artist, title) is None


@given(st.text())
def test_normalizing_is_idempotent(text: str) -> None:
    once = normalize_text(text)
    assert normalize_text(once) == once
