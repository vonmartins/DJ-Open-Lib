"""The M3U adapter class."""

from pathlib import Path

from tunedex.adapters.contract import (
    Capabilities,
    Detection,
    ReadOptions,
    ReadResult,
    WriteOptions,
    WritePlan,
)
from tunedex.adapters.m3u import reader, writer
from tunedex.model.library import Library


class M3UAdapter:
    """M3U/M3U8 playlists. ``relative_paths`` writes entries relative to each playlist file."""

    name = reader.NAME
    capabilities: Capabilities = writer.CAPABILITIES

    def __init__(self, *, relative_paths: bool = False) -> None:
        self.relative_paths = relative_paths

    def detect(self, location: Path) -> Detection:
        if not location.exists():
            return Detection(False, f"{location} does not exist")
        if location.is_file():
            if reader.is_playlist_file(location):
                return Detection(True, "M3U playlist file")
            return Detection(False, "not a .m3u or .m3u8 file")
        for path in location.rglob("*"):
            relative = path.relative_to(location)
            if any(part.startswith(".") for part in relative.parts):
                continue
            if path.is_file() and reader.is_playlist_file(path):
                return Detection(True, "directory with M3U playlists")
        return Detection(False, "no .m3u or .m3u8 files in the directory")

    def read(self, location: Path, options: ReadOptions | None = None) -> ReadResult:
        options = options or ReadOptions()
        tree = reader.TreeReader(options.path_mapping)
        library = tree.read(location)
        return ReadResult(library=library, warnings=tuple(tree.warnings))

    def plan_write(
        self, library: Library, location: Path, options: WriteOptions | None = None
    ) -> WritePlan:
        return writer.plan_write(
            library, location, options or WriteOptions(), relative_paths=self.relative_paths
        )
