-- Turns a copy of a real Mixxx profile's mixxxdb.sqlite into a committable fixture:
-- neutral paths and texts, no analysis caches, no machine paths. Run on a COPY:
--   cp profile/mixxxdb.sqlite real-2.5.6.sqlite && sqlite3 real-2.5.6.sqlite < sanitize.sql
-- Tracks are numbered by their original path order: /music/01.mp3, /music/02.mp3, ...

CREATE TEMP TABLE numbering AS
    SELECT id, printf('%02d', row_number() OVER (ORDER BY location)) AS n FROM track_locations;
UPDATE track_locations SET
    location = '/music/' || (SELECT n FROM numbering WHERE numbering.id = track_locations.id) || '.mp3',
    filename = (SELECT n FROM numbering WHERE numbering.id = track_locations.id) || '.mp3',
    directory = '/music';
UPDATE library SET
    artist = 'Artist ' || (SELECT n FROM numbering WHERE numbering.id = library.location),
    title = 'Track ' || (SELECT n FROM numbering WHERE numbering.id = library.location),
    album = '', album_artist = '', genre = '', composer = '', grouping = '', comment = '', url = '',
    wavesummaryhex = NULL, keys = NULL, keys_version = NULL, keys_sub_version = NULL,
    coverart_source = 0, coverart_type = 0, coverart_location = '', coverart_hash = 0,
    coverart_color = NULL, coverart_digest = NULL;
UPDATE cues SET label = '';
DELETE FROM track_analysis;
DELETE FROM LibraryHashes;
DELETE FROM directories;
INSERT INTO directories (directory) VALUES ('/music');
DELETE FROM settings WHERE name NOT LIKE 'mixxx.schema.%';
DROP TABLE IF EXISTS sqlite_stat4;
DROP TABLE IF EXISTS sqlite_stat1;
VACUUM;
