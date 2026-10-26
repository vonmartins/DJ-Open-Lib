-- djlib library database, schema version 1.
--
-- Conventions:
--   * Identifiers are canonical UUID text (36 characters).
--   * Times are integer microseconds (columns ending in _us).
--   * Dates are ISO 8601 text: YYYY-MM-DD for dates, YYYY-MM-DDTHH:MM:SS[.ffffff] for datetimes.
--   * "unmapped" columns hold JSON objects keyed by source format name, or NULL when empty.
--   * "position" columns give the order of rows under the same owner; gaps are allowed.
--   * The schema version lives in PRAGMA user_version, set by the migration runner.

-- Marks the file as a djlib database (ASCII "DJLB").
PRAGMA application_id = 1145719874;

-- Table: tracks. One row per audio file in the library.
CREATE TABLE tracks (
    id              TEXT PRIMARY KEY,
    -- Normalized path: the identity key used to recognize a file across imports.
    path            TEXT NOT NULL UNIQUE,
    -- Path exactly as received from the source.
    path_origin     TEXT NOT NULL,
    title           TEXT,
    artist          TEXT,
    album           TEXT,
    album_artist    TEXT,
    original_artist TEXT,
    genre           TEXT,
    year            INTEGER CHECK (year >= 0),
    track_number    INTEGER CHECK (track_number >= 0),
    disc_number     INTEGER CHECK (disc_number >= 0),
    bpm             REAL CHECK (bpm > 0),
    -- Canonical key: tonic pitch class (C = 0) plus 12 for minor keys.
    key_code        INTEGER CHECK (key_code BETWEEN 0 AND 23),
    -- Key text exactly as received from the source.
    key_original    TEXT,
    rating          INTEGER CHECK (rating BETWEEN 0 AND 5),
    -- #RRGGBB, upper case.
    color           TEXT CHECK (color GLOB '#[0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F]'),
    comment         TEXT,
    grouping        TEXT,
    composer        TEXT,
    producer        TEXT,
    lyricist        TEXT,
    remixer         TEXT,
    mix             TEXT,
    label           TEXT,
    play_count      INTEGER CHECK (play_count >= 0),
    date_added      TEXT,
    date_modified   TEXT,
    release_date    TEXT,
    last_played     TEXT,
    duration_us     INTEGER CHECK (duration_us >= 0),
    bitrate         INTEGER CHECK (bitrate >= 0),
    sample_rate     INTEGER CHECK (sample_rate >= 0),
    file_format     TEXT,
    energy          INTEGER CHECK (energy BETWEEN 0 AND 10),
    danceability    INTEGER CHECK (danceability BETWEEN 0 AND 10),
    happiness       INTEGER CHECK (happiness BETWEEN 0 AND 10),
    popularity      INTEGER CHECK (popularity BETWEEN 0 AND 10),
    extra1          TEXT,
    extra2          TEXT,
    unmapped        TEXT CHECK (unmapped IS NULL OR json_valid(unmapped))
) STRICT;

-- Table: cues. Cue points and loops of a track.
CREATE TABLE cues (
    track_id TEXT NOT NULL REFERENCES tracks (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    kind     TEXT NOT NULL CHECK (kind IN ('hot', 'memory', 'loop')),
    start_us INTEGER NOT NULL CHECK (start_us >= 0),
    -- Hot-cue pad index; a loop with a slot is a hot loop.
    slot     INTEGER CHECK (slot >= 0),
    name     TEXT,
    color    TEXT CHECK (color GLOB '#[0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F]'),
    -- Loops only: end after start, and whether the loop is active.
    end_us   INTEGER,
    active   INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
    unmapped TEXT CHECK (unmapped IS NULL OR json_valid(unmapped)),
    PRIMARY KEY (track_id, position),
    UNIQUE (track_id, slot),
    CHECK (
        (kind = 'loop' AND end_us > start_us)
        OR (kind <> 'loop' AND end_us IS NULL AND active = 0)
    )
) STRICT, WITHOUT ROWID;

-- Table: beat_markers. Beatgrid anchors of a track; several markers mean tempo changes.
CREATE TABLE beat_markers (
    track_id    TEXT NOT NULL REFERENCES tracks (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    position_us INTEGER NOT NULL CHECK (position_us >= 0),
    bpm         REAL NOT NULL CHECK (bpm > 0),
    -- Position of this beat within the bar.
    beat        INTEGER NOT NULL CHECK (beat BETWEEN 1 AND 4),
    PRIMARY KEY (track_id, position)
) STRICT, WITHOUT ROWID;

-- Table: tags. Distinct tag names (case-sensitive). Tag categories will attach here.
CREATE TABLE tags (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (name <> '')
) STRICT;

-- Table: track_tags. Ordered tags of each track.
CREATE TABLE track_tags (
    track_id TEXT NOT NULL REFERENCES tracks (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    tag_id   INTEGER NOT NULL REFERENCES tags (id),
    PRIMARY KEY (track_id, position),
    UNIQUE (track_id, tag_id)
) STRICT, WITHOUT ROWID;

CREATE INDEX track_tags_by_tag ON track_tags (tag_id);

-- Table: playlist_nodes. The playlist tree; root nodes have a NULL parent.
-- Only folders have children, only playlists have entries, only smartlists have rules.
CREATE TABLE playlist_nodes (
    id         TEXT PRIMARY KEY,
    -- Deleting a folder deletes everything below it.
    parent_id  TEXT REFERENCES playlist_nodes (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('folder', 'playlist', 'smartlist')),
    name       TEXT NOT NULL,
    -- Smartlists only: 'all' or 'any'.
    match_mode TEXT CHECK (match_mode IN ('all', 'any')),
    unmapped   TEXT CHECK (unmapped IS NULL OR json_valid(unmapped)),
    CHECK ((kind = 'smartlist') = (match_mode IS NOT NULL))
) STRICT;

CREATE UNIQUE INDEX playlist_nodes_by_parent ON playlist_nodes (coalesce(parent_id, ''), position);

-- Table: playlist_entries. Ordered tracks of each playlist; a track may repeat.
CREATE TABLE playlist_entries (
    node_id  TEXT NOT NULL REFERENCES playlist_nodes (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    -- Deleting a track removes it from every playlist.
    track_id TEXT NOT NULL REFERENCES tracks (id) ON DELETE CASCADE,
    PRIMARY KEY (node_id, position)
) STRICT, WITHOUT ROWID;

CREATE INDEX playlist_entries_by_track ON playlist_entries (track_id);

-- Table: smartlist_rules. Ordered rules of each smartlist, stored as data.
CREATE TABLE smartlist_rules (
    node_id     TEXT NOT NULL REFERENCES playlist_nodes (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    field       TEXT NOT NULL CHECK (field <> ''),
    operator    TEXT NOT NULL CHECK (operator <> ''),
    -- JSON array of the rule's values.
    values_json TEXT NOT NULL CHECK (json_valid(values_json) AND json_type(values_json) = 'array'),
    PRIMARY KEY (node_id, position)
) STRICT, WITHOUT ROWID;
