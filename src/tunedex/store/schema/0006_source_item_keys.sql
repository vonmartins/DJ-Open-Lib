-- tunedex library database, schema version 6: links from tracks to the source items they
-- were imported from.

-- Column: source_values.item_key. The source's own stable id of the item the track was
-- imported from (beets' items.id, Mixxx's library.id), or NULL when the source gives
-- none. Re-imports match by it before matching by path, so a track whose path was fixed
-- in tunedex stays linked to its item.
ALTER TABLE source_values ADD COLUMN item_key TEXT;

CREATE UNIQUE INDEX source_values_item_key ON source_values (source, item_key)
    WHERE item_key IS NOT NULL;
