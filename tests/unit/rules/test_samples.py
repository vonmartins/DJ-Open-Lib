"""Messy real-world names: the default fixes never fail, settle, and keep what they get right."""

from typing import Any

import pytest
import yaml

from support.rules_corpus import CORPUS
from tunedex.model.track import Track
from tunedex.rules.ruleset import defaults
from tunedex.rules.runner import run

SAMPLES = yaml.safe_load((CORPUS / "_samples.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", SAMPLES["file_names"], ids=lambda r: r["name"])
def test_untagged_file(row: dict[str, Any]) -> None:
    track = Track(path_origin=f"/music/{row['name']}")

    fixed, _edits, _warnings = run(defaults(), track)

    assert run(defaults(), fixed)[1] == []
    expected: dict[str, Any] = row.get("expected", {})
    for name, value in expected.items():
        assert getattr(fixed, name) == value


@pytest.mark.parametrize("title", SAMPLES["titles"])
def test_title(title: str) -> None:
    fixed, _edits, _warnings = run(defaults(), Track(path_origin="/music/x.mp3", title=title))

    assert run(defaults(), fixed)[1] == []
