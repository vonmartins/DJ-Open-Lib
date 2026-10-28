"""The beets source: the reading half of the adapter contract, used by imports."""

from pathlib import Path

from djlib.adapters.contract import (
    Capabilities,
    Detection,
    ReadOptions,
    ReadResult,
    WriteOptions,
    WritePlan,
)
from djlib.adapters.errors import AdapterError
from djlib.model.library import Library
from djlib.sources.beets import reader

CAPABILITIES = Capabilities(
    track_fields=frozenset(
        {
            "title",
            "artist",
            "album",
            "album_artist",
            "genre",
            "composer",
            "lyricist",
            "remixer",
            "grouping",
            "comment",
            "label",
            "year",
            "track_number",
            "disc_number",
            "bpm",
            "key",
            "key_original",
            "duration_us",
            "bitrate",
            "sample_rate",
            "file_format",
            "date_added",
            "release_date",
        }
    ),
    collection=True,
)


class BeetsSource:
    """A beets library database (``library.db``), or the directory holding it.

    ``music_dir`` is beets' music directory, needed for libraries that store paths
    relative to it (beets 2.14 and later).
    """

    name = reader.NAME
    display_name = "beets"
    capabilities: Capabilities = CAPABILITIES

    def __init__(self, *, music_dir: Path | None = None) -> None:
        self.music_dir = music_dir

    def detect(self, location: Path) -> Detection:
        reason = reader.not_beets(location)
        if reason is not None:
            return Detection(False, reason)
        return Detection(True, "beets library")

    def read(self, location: Path, options: ReadOptions | None = None) -> ReadResult:
        options = options or ReadOptions()
        beets = reader.BeetsReader(options.path_mapping, self.music_dir)
        tracks = beets.read(location)
        return ReadResult(
            library=Library.build(tracks), warnings=tuple(beets.warnings), keys=beets.keys
        )

    def plan_write(
        self, library: Library, location: Path, options: WriteOptions | None = None
    ) -> WritePlan:
        raise AdapterError("beets libraries are only read; djlib never writes to them")
