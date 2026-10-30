-- tunedex library database, schema version 5: where each exported node lives in its target.

-- Column: sync_state.target_path. JSON array of the names leading to the node in the
-- target, such as ["Playlists", "Techno / Peak"] for Mixxx; NULL when the target keeps
-- the library's own tree. Imports from the same location skip what tunedex wrote there.
ALTER TABLE sync_state ADD COLUMN target_path TEXT
    CHECK (target_path IS NULL OR json_valid(target_path));
