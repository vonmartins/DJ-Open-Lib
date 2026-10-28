"""The Mixxx adapter class."""

import datetime
from collections.abc import Callable
from pathlib import Path

from djlib.adapters.contract import (
    Capabilities,
    Detection,
    ReadOptions,
    ReadResult,
    WriteOptions,
    WritePlan,
)
from djlib.adapters.mixxx import reader
from djlib.adapters.mixxx.running import mixxx_running
from djlib.adapters.mixxx.writer import UPDATED_FIELDS, MixxxWriter
from djlib.model.cue import CueKind
from djlib.model.library import Library

CAPABILITIES = Capabilities(
    track_fields=frozenset(
        {
            "artist",
            "title",
            "album",
            "album_artist",
            "genre",
            "composer",
            "grouping",
            "comment",
            "year",
            "track_number",
            "duration_us",
            "bitrate",
            "sample_rate",
            "file_format",
            "bpm",
            "key",
            "key_original",
            "rating",
            "color",
            "play_count",
            "last_played",
            "date_added",
        }
    ),
    cue_kinds=frozenset({CueKind.HOT, CueKind.MEMORY, CueKind.LOOP}),
    beatgrid=True,
    collection=True,
    updated_fields=UPDATED_FIELDS,
)


class MixxxAdapter:
    """A Mixxx library database (``mixxxdb.sqlite``), or the settings directory holding it."""

    name = reader.NAME
    display_name = "Mixxx"
    capabilities: Capabilities = CAPABILITIES

    def __init__(
        self,
        *,
        running: Callable[[], bool] = mixxx_running,
        clock: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        """``running`` tells whether Mixxx runs; writes are refused while it does."""
        self._running = running
        self._clock = clock or (lambda: datetime.datetime.now(datetime.UTC))

    def detect(self, location: Path) -> Detection:
        path = reader.database_path(location)
        if not path.is_file():
            return Detection(False, f"{path} does not exist")
        version = reader.schema_version(path)
        if version is None:
            return Detection(False, "no Mixxx schema version found in the database")
        return Detection(True, f"Mixxx library, schema version {version}")

    def read(self, location: Path, options: ReadOptions | None = None) -> ReadResult:
        options = options or ReadOptions()
        mixxx = reader.MixxxReader(options.path_mapping)
        library = mixxx.read(location)
        return ReadResult(library=library, warnings=tuple(mixxx.warnings))

    def plan_write(
        self, library: Library, location: Path, options: WriteOptions | None = None
    ) -> WritePlan:
        writer = MixxxWriter(CAPABILITIES, self._running, now=self._clock())
        return writer.plan(library, location, options or WriteOptions())
