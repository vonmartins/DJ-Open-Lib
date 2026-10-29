"""The bundled fixes against their case tables, the clean corpus and properties."""

import dataclasses
import unicodedata
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from djlib.model.track import Track
from djlib.rules.fixes import (
    BY_NAME,
    FIXES,
    NAME_FIELDS,
    Fix,
    apply,
    fix_encoding_text,
    fix_options,
    run_fixes,
)
from support.rules_corpus import CORPUS, Case, clean, load
from support.text import clean_text, dirty_text

TABLES = sorted(p.stem for p in CORPUS.glob("*.yaml") if p.stem != "clean")
CASES = [case for name in TABLES for case in load(name)]
DEFAULTS = [fix for fix in FIXES if fix.on]


def _fix_of(case: Case) -> Fix:
    return BY_NAME[case.source.split(".yaml")[0]]


def run_all(track: Track, fixes: list[Fix]) -> Track:
    return run_fixes(track, [(fix, fix_options(fix, None)) for fix in fixes])[0]


def test_every_fix_has_a_table() -> None:
    assert sorted(fix.name for fix in FIXES) == TABLES


@pytest.mark.parametrize("name", TABLES)
def test_tables_meet_the_bar(name: str) -> None:
    cases = load(name)
    changes = [c for c in cases if c.expected is not None]
    keeps = [c for c in cases if c.expected is None]
    assert len(changes) >= 10, f"{name}: needs at least 10 rows that change"
    assert len(keeps) >= 10, f"{name}: needs at least 10 rows that must not change"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case: Case) -> None:
    fix = _fix_of(case)
    options = fix_options(fix, case.options)

    changes = apply(fix, case.track, options)

    if case.expected is None:
        assert changes == {}, f"{case.id}: must not change"
        return
    assert changes == case.expected
    again = apply(fix, dataclasses.replace(case.track, **changes), options)
    assert again == {}, f"{case.id}: the fix is not idempotent"


@pytest.mark.parametrize("track", clean(), ids=lambda t: t.title or t.artist or t.path)
def test_clean_corpus_unchanged(track: Track) -> None:
    assert run_all(track, DEFAULTS) == track


TEXT_FIELDS = st.sampled_from(["title", "artist", "album", "remixer", "comment"])


def tracks(text: st.SearchStrategy[str]) -> st.SearchStrategy[Track]:
    return st.builds(
        lambda title, artist, album, name: Track(
            path_origin=f"/music/{name}.mp3", title=title, artist=artist, album=album
        ),
        st.one_of(st.none(), text),
        st.one_of(st.none(), text),
        st.one_of(st.none(), text),
        st.text(st.characters(categories=("L", "N")), min_size=1, max_size=12),
    )


@settings(max_examples=300, deadline=None)
@given(track=tracks(st.one_of(dirty_text, clean_text)))
def test_defaults_are_idempotent_and_total(track: Track) -> None:
    once = run_all(track, DEFAULTS)
    assert run_all(once, DEFAULTS) == once


@settings(max_examples=200, deadline=None)
@given(track=tracks(st.one_of(dirty_text, clean_text)), fix=st.sampled_from(FIXES))
def test_each_fix_is_idempotent_and_keeps_to_its_fields(track: Track, fix: Fix) -> None:
    options = fix_options(fix, None)
    changes = apply(fix, track, options)

    assert set(changes) <= set(options["fields"]) | set(fix.fields)
    fixed = dataclasses.replace(track, **changes)  # valid model values
    assert apply(fix, fixed, options) == {}


def _letters(value: Any) -> list[str]:
    """Letters and digits, as full-width and other compatibility forms read."""
    text = unicodedata.normalize("NFKC", value or "")
    return sorted(c for c in text if c.isalnum())


@settings(max_examples=300, deadline=None)
@given(track=tracks(clean_text))
def test_letters_of_clean_text_survive(track: Track) -> None:
    """Fixes may only lose letters they target; on clean text, only repairs change them."""
    fixed = run_all(track, DEFAULTS)
    for name in ("title", "album"):
        before = getattr(track, name)
        if before is None or fix_encoding_text(before) != before:
            continue
        assert _letters(getattr(fixed, name)) == _letters(before)


def test_field_options_are_checked() -> None:
    with pytest.raises(ValueError, match="unknown options"):
        fix_options(BY_NAME["remove_urls"], {"keep": ["x"]})
    with pytest.raises(ValueError, match="fields must be a list of text fields"):
        fix_options(BY_NAME["remove_urls"], {"fields": ["bpm"]})
    assert fix_options(BY_NAME["fix_case"], {"keep": ["DJ"]})["keep"] == ("DJ",)
    assert "title" in NAME_FIELDS
