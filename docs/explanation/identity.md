# Track identity

A DJ library outlives folders, disks and computers. djlib therefore separates *which track this is* from *where its file is*.

## The id

Every track gets a random UUID the first time it enters the library. The id never changes: not when the file moves, not when its tags change, not when it is enriched. Playlists, cues and history refer to the id, so they survive all of that.

The id is never derived from the path or the content of the file. Two copies of the same song are two tracks with two ids until you [merge them](../guides/duplicates.md).

## The path

Each track also has a **path**, normalized so that the same file is always written the same way:

- `/` as separator, on every system;
- an upper-case drive letter on Windows (`C:/Music/...`);
- Unicode in one form (NFC), so that `é` typed two ways is the same;
- `.` and `..` resolved, with no trailing separator.

The path as the source wrote it is kept too, as `path_origin`.

## Recognizing a track again

When a scan or an import sees a file, djlib has to decide whether it is a track it already knows.

- **A folder scan** matches by path. A file that disappeared from one place and appeared in another, with the same size and quick hash, is recognized as **moved**, not as one track removed and another added.
- **An import** matches by path the first time. djlib then remembers the source's own id for the item, such as the Mixxx track id or the beets item id, and uses it from then on. A track whose path you fix in djlib therefore stays linked to its Mixxx or beets item.
- **[`relocate`](../guides/relocate.md)** changes only the path of a known track, so everything else about it stays.

## Your edits and theirs

djlib remembers the values each source gave a track the last time. When the source changes a field later:

- if you did not edit that field in djlib, the source's new value is taken;
- if you did, your value stays, and the plan lists a **conflict** so that you can decide.

This is how you can keep using Mixxx or beets alongside djlib and re-import whenever you like, without losing work on either side.
