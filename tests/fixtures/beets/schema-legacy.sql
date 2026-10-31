-- beets library schema before the beets 2.x list fields and relative paths: single
-- genre, composer and lyricist columns, absolute paths. Table definitions only.
CREATE TABLE items (id INTEGER PRIMARY KEY, path BLOB, album_id INTEGER, title TEXT, artist TEXT, artist_sort TEXT, artist_credit TEXT, album TEXT, albumartist TEXT, albumartist_sort TEXT, albumartist_credit TEXT, genre TEXT, style TEXT, discogs_albumid INTEGER, discogs_artistid INTEGER, discogs_labelid INTEGER, lyricist TEXT, composer TEXT, composer_sort TEXT, work TEXT, mb_workid TEXT, work_disambig TEXT, arranger TEXT, grouping TEXT, year INTEGER, month INTEGER, day INTEGER, track INTEGER, tracktotal INTEGER, disc INTEGER, disctotal INTEGER, lyrics TEXT, comments TEXT, bpm INTEGER, comp INTEGER, mb_trackid TEXT, mb_albumid TEXT, mb_artistid TEXT, mb_albumartistid TEXT, mb_releasetrackid TEXT, trackdisambig TEXT, albumtype TEXT, albumtypes TEXT, label TEXT, acoustid_fingerprint TEXT, acoustid_id TEXT, mb_releasegroupid TEXT, asin TEXT, isrc TEXT, catalognum TEXT, script TEXT, language TEXT, country TEXT, albumstatus TEXT, media TEXT, albumdisambig TEXT, releasegroupdisambig TEXT, disctitle TEXT, encoder TEXT, rg_track_gain REAL, rg_track_peak REAL, rg_album_gain REAL, rg_album_peak REAL, r128_track_gain INTEGER, r128_album_gain INTEGER, original_year INTEGER, original_month INTEGER, original_day INTEGER, initial_key TEXT, length REAL, bitrate INTEGER, format TEXT, samplerate INTEGER, bitdepth INTEGER, channels INTEGER, mtime REAL, added REAL);
CREATE TABLE item_attributes (
                    id INTEGER PRIMARY KEY,
                    entity_id INTEGER,
                    key TEXT,
                    value TEXT,
                    UNIQUE(entity_id, key) ON CONFLICT REPLACE);
CREATE INDEX item_attributes_by_entity
                    ON item_attributes (entity_id);
CREATE TABLE albums (id INTEGER PRIMARY KEY, artpath BLOB, added REAL, albumartist TEXT, albumartist_sort TEXT, albumartist_credit TEXT, album TEXT, genre TEXT, style TEXT, discogs_albumid INTEGER, discogs_artistid INTEGER, discogs_labelid INTEGER, year INTEGER, month INTEGER, day INTEGER, disctotal INTEGER, comp INTEGER, mb_albumid TEXT, mb_albumartistid TEXT, albumtype TEXT, albumtypes TEXT, label TEXT, mb_releasegroupid TEXT, asin TEXT, catalognum TEXT, script TEXT, language TEXT, country TEXT, albumstatus TEXT, albumdisambig TEXT, releasegroupdisambig TEXT, rg_album_gain REAL, rg_album_peak REAL, r128_album_gain INTEGER, original_year INTEGER, original_month INTEGER, original_day INTEGER);
CREATE TABLE album_attributes (
                    id INTEGER PRIMARY KEY,
                    entity_id INTEGER,
                    key TEXT,
                    value TEXT,
                    UNIQUE(entity_id, key) ON CONFLICT REPLACE);
CREATE INDEX album_attributes_by_entity
                    ON album_attributes (entity_id);
