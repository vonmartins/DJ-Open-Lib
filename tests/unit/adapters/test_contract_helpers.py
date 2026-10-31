from pathlib import Path

import pytest

from support.adapter_contract import (
    assert_plan_writes_nothing,
    assert_read_only,
    write_plan_to_disk,
)
from tunedex.adapters.contract import (
    Capabilities,
    Detection,
    FileChange,
    ReadOptions,
    ReadResult,
    WriteOptions,
    WritePlan,
)
from tunedex.model.library import Library


class MisbehavingAdapter:
    """Writes during read and plan_write, which the contract forbids."""

    name = "rude"
    capabilities = Capabilities(track_fields=frozenset())

    def detect(self, location: Path) -> Detection:
        return Detection(True, "")

    def read(self, location: Path, options: ReadOptions | None = None) -> ReadResult:
        (location / "touched").write_text("x", encoding="utf-8")
        return ReadResult(library=Library())

    def plan_write(
        self, library: Library, location: Path, options: WriteOptions | None = None
    ) -> WritePlan:
        (location / "a.m3u8").write_text("changed", encoding="utf-8")
        return WritePlan(adapter=self.name, location=location)


def test_read_violation_detected(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="read changed"):
        assert_read_only(MisbehavingAdapter(), tmp_path)


def test_plan_violation_detected(tmp_path: Path) -> None:
    (tmp_path / "a.m3u8").write_text("original", encoding="utf-8")
    with pytest.raises(AssertionError, match="plan_write changed"):
        assert_plan_writes_nothing(MisbehavingAdapter(), Library(), tmp_path)


def test_write_plan_to_disk(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "a.m3u8"
    plan = WritePlan(
        adapter="x",
        location=tmp_path,
        changes=(FileChange(path=target, content=b"#EXTM3U\n", base_sha256=None, description=""),),
    )
    write_plan_to_disk(plan)
    assert target.read_bytes() == b"#EXTM3U\n"
