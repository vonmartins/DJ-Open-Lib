import pytest

from djlib.adapters.pathmap import PathMapping, PathRule
from djlib.model.errors import ValidationError

MAPPING = PathMapping((PathRule("/mnt/music", "D:/Music"),))


def test_mapping_on_write() -> None:
    assert MAPPING.to_target("/mnt/music/House/a.mp3") == "D:/Music/House/a.mp3"


def test_mapping_on_read() -> None:
    assert MAPPING.to_library(r"D:\Music\House\a.mp3") == "/mnt/music/House/a.mp3"


def test_component_boundary() -> None:
    assert MAPPING.to_target("/mnt/musicals/a.mp3") == "/mnt/musicals/a.mp3"


def test_exact_prefix() -> None:
    assert MAPPING.to_target("/mnt/music") == "D:/Music"


def test_first_rule_wins() -> None:
    mapping = PathMapping(
        (PathRule("/mnt/music/House", "E:/House"), PathRule("/mnt/music", "D:/Music"))
    )
    assert mapping.to_target("/mnt/music/House/a.mp3") == "E:/House/a.mp3"
    assert mapping.to_target("/mnt/music/Techno/b.mp3") == "D:/Music/Techno/b.mp3"


def test_no_match_returns_normalized_path() -> None:
    assert MAPPING.to_target("/other//a.mp3") == "/other/a.mp3"
    assert PathMapping().to_library(r"c:\x\a.mp3") == "C:/x/a.mp3"


def test_prefixes_are_normalized() -> None:
    rule = PathRule("/mnt/music/", r"d:\Music\\")
    assert (rule.library, rule.target) == ("/mnt/music", "D:/Music")


def test_root_prefixes() -> None:
    mapping = PathMapping((PathRule("/", "C:/"),))
    assert mapping.to_target("/a/b.mp3") == "C:/a/b.mp3"
    assert mapping.to_library("C:/a/b.mp3") == "/a/b.mp3"


def test_relative_prefix_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        PathRule("music", "D:/Music")
    assert (excinfo.value.entity, excinfo.value.field) == ("PathRule", "library")
