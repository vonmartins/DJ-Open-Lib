-- tunedex library database, schema version 2: file state for folder scans.

-- Table: file_state. What a folder scan last saw of a track's file.
CREATE TABLE file_state (
    track_id       TEXT PRIMARY KEY REFERENCES tracks (id) ON DELETE CASCADE,
    -- Size in bytes and modification time in nanoseconds at the last scan; a rescan
    -- re-reads the file only when either differs.
    size           INTEGER NOT NULL CHECK (size >= 0),
    mtime_ns       INTEGER NOT NULL,
    -- SHA-256 hex of the size and the first and last 16 KiB; used to detect moves.
    quick_hash     TEXT NOT NULL CHECK (length(quick_hash) = 64),
    -- 1 when the file was not found at its path by the last scan of its folder.
    missing        INTEGER NOT NULL DEFAULT 0 CHECK (missing IN (0, 1)),
    -- UTC time of the last scan that read or checked the file.
    scanned_at     TEXT NOT NULL,
    -- JSON object: field values read from the file at the last scan (merge base).
    scanned_values TEXT NOT NULL CHECK (json_valid(scanned_values) AND json_type(scanned_values) = 'object')
) STRICT;
