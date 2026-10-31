"""Rules files and running them (specs/rules-engine)."""

import datetime
import textwrap
from pathlib import Path

import pytest
import yaml

from tunedex.model.key import Key, Mode
from tunedex.model.track import Track
from tunedex.rules import RuleError
from tunedex.rules.ruleset import defaults, load, parse
from tunedex.rules.runner import run


def rules(text: str):
    return parse(yaml.safe_load(textwrap.dedent(text)))


def names(ruleset) -> list[str]:
    return [fix.name for fix, _ in ruleset.fixes]


def test_defaults_without_a_file() -> None:
    assert "remove_urls" in names(defaults())
    assert "fix_case" not in names(defaults())
    assert names(parse(None)) == names(defaults())
    assert names(parse({})) == names(defaults())


def test_fix_disabled() -> None:
    ruleset = rules("fixes: {extract_featured: false}")
    track = Track(path_origin="/m/a.mp3", artist="Echo Unit", title="Storm (feat. Mira)")

    assert "extract_featured" not in names(ruleset)
    assert run(ruleset, track)[1] == []


def test_fix_enabled_with_options() -> None:
    ruleset = rules("fixes: {fix_case: {keep: [DJ]}}")
    track = Track(path_origin="/m/a.mp3", title="Mix", album="dj kicks vol iv")

    _track, edits, _ = run(ruleset, track)

    assert [(e.field, e.after, e.by) for e in edits] == [("album", "DJ Kicks Vol IV", "fix_case")]


def test_replace() -> None:
    ruleset = rules(
        r"""
        fixes: {}
        rules:
          - id: no-year
            when: {field: title, op: matches, value: ' \[\d{4}\]$'}
            then: {replace: title, pattern: ' \[\d{4}\]$', with: ''}
        """
    )

    track, edits, _ = run(ruleset, Track(path_origin="/m/a.mp3", title="Glue [2016]"))

    assert track.title == "Glue"
    assert [(e.before, e.after, e.by) for e in edits] == [("Glue [2016]", "Glue", "no-year")]


def test_replace_with_groups_and_unicode() -> None:
    ruleset = rules(
        r"""
        rules:
          - id: swap
            then: {replace: title, pattern: '^(\w+) - (\w+)$', with: '\2 - \1'}
        """
    )

    assert run(ruleset, Track(path_origin="/m/a.mp3", title="Группа - Кровь"))[0].title == (
        "Кровь - Группа"
    )


def test_set_values_of_every_kind() -> None:
    ruleset = rules(
        """
        rules:
          - id: tidy
            when: [{field: genre, op: equals, value: DnB}]
            then:
              - {set: genre, value: Drum And Bass}
              - {set: bpm, value: 174}
              - {set: key, value: 1m}
              - {set: release_date, value: 2016-03-04}
              - {set: tags, value: [Peak, Dark]}
              - {set: comment, value: ''}
        """
    )
    track = Track(path_origin="/m/a.mp3", genre="DnB", comment="old")

    fixed = run(ruleset, track)[0]

    assert (fixed.genre, fixed.bpm, fixed.key) == (
        "Drum And Bass",
        174,
        Key(tonic=9, mode=Mode.MINOR),
    )
    assert (fixed.release_date, fixed.tags, fixed.comment) == (
        datetime.date(2016, 3, 4),
        ("Peak", "Dark"),
        None,
    )


def test_any_match() -> None:
    ruleset = rules(
        """
        fixes: {}
        rules:
          - id: dnb
            match: any
            when:
              - {field: genre, op: equals, value: Drum n Bass}
              - {field: genre, op: equals, value: DnB}
            then: {set: genre, value: Drum And Bass}
        """
    )

    assert run(ruleset, Track(path_origin="/m/a.mp3", genre="dnb"))[0].genre == "Drum And Bass"
    assert run(ruleset, Track(path_origin="/m/a.mp3", genre="House"))[0].genre == "House"


def test_value_the_field_rejects_is_a_warning() -> None:
    ruleset = rules("rules: [{id: bad, then: {set: rating, value: 9}}]")
    track = Track(path_origin="/m/a.mp3", title="A")

    fixed, edits, warnings = run(ruleset, track)

    assert fixed == track and edits == []
    assert len(warnings) == 1 and "rule bad not applied" in warnings[0]


def test_several_fixes_on_one_field_are_named_together() -> None:
    track = Track(path_origin="/m/a.mp3", title="Glue\u00a0 (freebeats.com)")

    _fixed, edits, _ = run(defaults(), track)

    assert [(e.field, e.after, e.by) for e in edits] == [
        ("title", "Glue", "normalize_characters, remove_urls")
    ]


def test_second_run_changes_nothing() -> None:
    ruleset = rules(
        r"""
        rules:
          - {id: no-year, then: {replace: title, pattern: ' \[\d{4}\]$', with: ''}}
        """
    )
    track = Track(
        path_origin="/m/Echo Unit - Storm.mp3",
        artist="Echo Unit",
        title="03 - Storm (feat. Mira) [2016] [aB3x-9Kq_Zt]",
    )

    once = run(ruleset, track)[0]

    assert once.title == "Storm" and once.artist == "Echo Unit feat. Mira"
    assert run(ruleset, once)[1] == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("fixes: {remove_url: false}", "fixes.remove_url: unknown fix"),
        ("fixes: {remove_urls: {keep: [x]}}", "remove_urls: unknown options keep"),
        ("fixes: {fix_case: {fields: [bpm]}}", "fields must be a list of text fields"),
        ("fixes: {remove_urls: 3}", "expected true, false or options"),
        (
            "rules: [{when: {field: title, op: empty}, then: {set: title, value: x}}]",
            "rules[0]: needs an id",
        ),
        (
            "rules: [{id: r, when: {field: titel, op: empty}, then: {set: title, value: x}}]",
            "rules[0] (r): unknown field 'titel'",
        ),
        (
            "rules: [{id: r, when: {field: title, op: bigger, value: 1},"
            " then: {set: title, value: x}}]",
            "operator 'bigger' does not apply",
        ),
        (
            "rules: [{id: r, when: {field: title, op: matches, value: '('},"
            " then: {set: title, value: x}}]",
            "rules[0] (r): title: invalid regular expression",
        ),
        ("rules: [{id: r, then: {replace: title, pattern: '('}}]", "invalid regular expression"),
        ("rules: [{id: r, then: {replace: bpm, pattern: x}}]", "replace works on text fields"),
        ("rules: [{id: r, then: {delete: title}}]", "an action needs replace or set"),
        ("rules: [{id: r}]", "then must be an action"),
        ("rules: [{id: r, match: some, then: {set: title, value: x}}]", "match must be all or any"),
        ("rules: [{id: remove_urls, then: {set: title, value: x}}]", "the id is already used"),
        (
            "rules: [{id: r, then: {set: t, value: x}}, {id: r, then: {set: title, value: x}}]",
            "unknown field 't'",
        ),
        ("colors: {}", "unknown sections: colors"),
        (
            "rename: {pattern: '{artist} - {name}'}",
            "rename: pattern '{artist} - {name}': unknown field 'name'",
        ),
        ("rename: '{artist}'", "rename: expected a mapping with a pattern"),
        ("rename: {pattern: '{title}', case: upper}", "rename: expected a mapping with a pattern"),
        ("rules: {}", "rules: expected a list"),
        ("- a\n- b", "expected a mapping"),
    ],
)
def test_invalid_rules_refused(text: str, message: str) -> None:
    with pytest.raises(RuleError) as caught:
        parse(yaml.safe_load(text), origin="rules.yaml")

    assert message in str(caught.value)


def test_every_error_is_reported() -> None:
    with pytest.raises(RuleError) as caught:
        rules(
            """
            fixes: {remove_url: false}
            rules:
              - {id: a, then: {set: titel, value: x}}
              - {id: b, then: {replace: title, pattern: '('}}
            """
        )

    message = str(caught.value)
    assert "remove_url" in message and "rules[0] (a)" in message and "rules[1] (b)" in message


def test_only() -> None:
    ruleset = rules("rules: [{id: mine, then: {set: grouping, value: x}}]")

    chosen = ruleset.only(["mine", "fix_case", "remove_urls"])

    assert [f.name for f, _ in chosen.fixes] == ["remove_urls", "fix_case"]
    assert [r.id for r in chosen.rules] == ["mine"]
    with pytest.raises(RuleError, match="unknown fixes or rules: remove_url"):
        ruleset.only(["remove_url"])


def test_load_from_a_file(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("fixes: {extract_featured: false}\n")
    assert "extract_featured" not in names(load(path))

    path.write_text("fixes: [\n")
    with pytest.raises(RuleError, match="not valid YAML"):
        load(path)
    with pytest.raises(RuleError, match="cannot read"):
        load(tmp_path / "missing.yaml")


def test_rename_pattern() -> None:
    ruleset = parse(yaml.safe_load("rename: {pattern: '{artist} - {title} [{year}]'}"))
    assert ruleset.rename is not None
    assert ruleset.rename.fields == ("artist", "title", "year")
    assert ruleset.only(["remove_urls"]).rename == ruleset.rename
    assert parse(yaml.safe_load("fixes: {}")).rename is None
