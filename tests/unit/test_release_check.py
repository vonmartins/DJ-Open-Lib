from pathlib import Path

import pytest

from release_check import ReleaseError, release_notes

CHANGELOG = """# Changelog

## [Unreleased]

## [0.2.0] - 2027-01-10

### Added

- Rekordbox import.

## [0.1.0] - 2026-11-01

First release.

[Unreleased]: https://github.com/vonmartins/tunedex/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/vonmartins/tunedex/compare/v0.1.0...v0.2.0
"""


def project(tmp_path: Path, version: str, changelog: str = CHANGELOG) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "tunedex"\nversion = "{version}"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def test_notes_of_a_matching_version(tmp_path: Path) -> None:
    root = project(tmp_path, "0.2.0")
    assert release_notes("v0.2.0", root) == "### Added\n\n- Rekordbox import.\n"


def test_the_last_section_stops_at_the_links(tmp_path: Path) -> None:
    root = project(tmp_path, "0.1.0")
    assert release_notes("0.1.0", root) == "First release.\n"


def test_a_tag_that_does_not_match_the_package(tmp_path: Path) -> None:
    root = project(tmp_path, "0.1.0")
    with pytest.raises(ReleaseError, match=r"0\.1\.1 does not match pyproject\.toml \(0\.1\.0\)"):
        release_notes("v0.1.1", root)


def test_a_version_without_a_section(tmp_path: Path) -> None:
    root = project(tmp_path, "0.3.0")
    with pytest.raises(ReleaseError, match=r"no section for 0\.3\.0"):
        release_notes("0.3.0", root)


def test_an_empty_section(tmp_path: Path) -> None:
    root = project(tmp_path, "0.1.0", "## [0.1.0] - 2026-11-01\n\n## [0.0.1]\n\nx\n")
    with pytest.raises(ReleaseError, match="empty"):
        release_notes("0.1.0", root)
