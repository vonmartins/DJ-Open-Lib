-- djlib library database, schema version 7: duplicate tracks merged into another, and
-- groups of tracks marked as not duplicates.

-- Table: merges. What a track merged into another left behind: its path, or one source
-- item it was linked to. Scans skip the path and imports match the item to `into_track`,
-- so a merged duplicate does not come back. Exactly one of path or (source, item_key).
CREATE TABLE merges (
    path       TEXT,
    source     TEXT,
    item_key   TEXT,
    into_track TEXT NOT NULL REFERENCES tracks (id) ON DELETE CASCADE,
    CHECK ((path IS NULL) <> (source IS NULL)),
    CHECK ((source IS NULL) = (item_key IS NULL))
) STRICT;

CREATE UNIQUE INDEX merges_by_path ON merges (path) WHERE path IS NOT NULL;
CREATE UNIQUE INDEX merges_by_item ON merges (source, item_key) WHERE source IS NOT NULL;
CREATE INDEX merges_by_track ON merges (into_track);

-- Table: not_duplicates. Sets of tracks the user marked as not duplicates of each other;
-- a group whose tracks all belong to one set is not reported again.
CREATE TABLE not_duplicates (
    set_id   INTEGER NOT NULL,
    track_id TEXT NOT NULL REFERENCES tracks (id) ON DELETE CASCADE,
    PRIMARY KEY (set_id, track_id)
) STRICT, WITHOUT ROWID;
