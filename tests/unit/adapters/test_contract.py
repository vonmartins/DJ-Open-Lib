from pathlib import Path

import pytest

from tunedex.adapters.contract import (
    Adapter,
    Capabilities,
    Detection,
    FileChange,
    Loss,
    ReadOptions,
    ReadResult,
    WriteOptions,
    WritePlan,
)
from tunedex.model.library import Library


class FakeAdapter:
    name = "fake"
    capabilities = Capabilities(track_fields=frozenset({"title"}))

    def detect(self, location: Path) -> Detection:
        return Detection(False, "never matches")

    def read(self, location: Path, options: ReadOptions | None = None) -> ReadResult:
        return ReadResult(library=Library())

    def plan_write(
        self, library: Library, location: Path, options: WriteOptions | None = None
    ) -> WritePlan:
        return WritePlan(adapter=self.name, location=location)


def test_fake_adapter_satisfies_protocol(tmp_path: Path) -> None:
    adapter: Adapter = FakeAdapter()

    assert adapter.read(tmp_path).library == Library()
    assert adapter.plan_write(Library(), tmp_path).changes == ()


def test_file_change_action(tmp_path: Path) -> None:
    create = FileChange(path=tmp_path / "a", content=b"x", base_sha256=None, description="new")
    update = FileChange(path=tmp_path / "a", content=b"x", base_sha256="0" * 64, description="")

    assert (create.action, update.action) == ("create", "update")


def test_file_change_needs_absolute_path() -> None:
    with pytest.raises(ValueError):
        FileChange(path=Path("a.m3u8"), content=b"", base_sha256=None, description="")


def test_loss_examples_limited() -> None:
    Loss(kind="cues", description="", count=9, examples=tuple("abcde"))
    with pytest.raises(ValueError):
        Loss(kind="cues", description="", count=9, examples=tuple("abcdef"))


def test_loss_needs_a_count() -> None:
    with pytest.raises(ValueError):
        Loss(kind="cues", description="", count=0)


def test_options_defaults() -> None:
    assert WriteOptions().selection is None
    assert ReadOptions().path_mapping.rules == ()
