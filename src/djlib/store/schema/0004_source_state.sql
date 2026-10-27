-- djlib library database, schema version 4: import sources and their merge bases.

-- Table: sources. One row per import source (an adapter at a location).
CREATE TABLE sources (
    -- "<adapter>-<12 hex digits of the location's hash>".
    name         TEXT PRIMARY KEY,
    -- The folder holding the source's playlists; NULL once the user deletes it, so
    -- the next import creates it again.
    root_node_id TEXT REFERENCES playlist_nodes (id) ON DELETE SET NULL,
    -- UTC time of the last applied import.
    imported_at  TEXT NOT NULL
) STRICT;

-- Table: source_values. What an import last read of each track (the merge base).
CREATE TABLE source_values (
    source       TEXT NOT NULL REFERENCES sources (name) ON DELETE CASCADE,
    track_id     TEXT NOT NULL REFERENCES tracks (id) ON DELETE CASCADE,
    -- JSON object: field name -> value as canonical JSON (cues and beat grid included).
    field_values TEXT NOT NULL
        CHECK (json_valid(field_values) AND json_type(field_values) = 'object'),
    PRIMARY KEY (source, track_id)
) STRICT;
