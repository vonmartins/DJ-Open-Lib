-- djlib library database, schema version 3: revision counter and export sync state.

-- Table: store_meta. One row holding the library revision.
CREATE TABLE store_meta (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    -- Incremented by every committed write to tracks, file states or playlists; plans
    -- record it so that applying them can refuse a library that changed meanwhile.
    revision INTEGER NOT NULL CHECK (revision >= 0)
) STRICT;

INSERT INTO store_meta (id, revision) VALUES (1, 0);

-- Table: sync_state. What was last exported of each node to each target.
CREATE TABLE sync_state (
    -- Export target name: "<adapter>-<12 hex digits of the location's hash>".
    target      TEXT NOT NULL,
    node_id     TEXT NOT NULL REFERENCES playlist_nodes (id) ON DELETE CASCADE,
    -- SHA-256 hex of the node as exported; a modified export rewrites nodes whose
    -- fingerprint differs.
    fingerprint TEXT NOT NULL CHECK (length(fingerprint) = 64),
    -- UTC time of the export.
    synced_at   TEXT NOT NULL,
    PRIMARY KEY (target, node_id)
) STRICT;
