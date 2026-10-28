"""The Mixxx adapter class (reading only, for now)."""

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
from djlib.adapters.mixxx import reader
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
)


class MixxxAdapter:
    """A Mixxx library database (``mixxxdb.sqlite``), or the settings directory holding it."""

    name = reader.NAME
    display_name = "Mixxx"
    capabilities: Capabilities = CAPABILITIES

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
        raise AdapterError("writing to Mixxx is not supported yet")
