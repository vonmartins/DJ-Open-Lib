# Importing from beets

Bring in the tracks of a [beets](https://beets.io) library with all their tags.

```sh
djlib import beets                              # beets' own library: show the plan
djlib import beets ~/Music/.beets.db --apply    # a given library file
```

beets does not need to be installed. Its database and your music files are only read.

## What is imported

Every track, with its tags: genre, label, key, MusicBrainz and Discogs ids, ISRC and more. Tags djlib has no field for are kept with the track, so nothing is thrown away. Albums do not become playlists.

## Where djlib finds the library

Without a path, djlib looks where beets does:

1. `$BEETSDIR`;
2. the `library` setting of beets' `config.yaml`;
3. `~/.config/beets/library.db`.

Newer beets versions store paths relative to the music directory. djlib takes that directory from `directory` in the same `config.yaml`, or from `--music-dir`:

```sh
djlib import beets ~/Music/.beets.db --music-dir ~/Music
```

## Importing again

Tracks are matched by path the first time, and to the same beets item afterwards. A track whose path you fix in djlib therefore stays linked to beets. Fields you edit in djlib win over later beets changes, and the plan lists them as conflicts.

## A library made on another computer

If beets runs on a server or a NAS, its paths may not exist where djlib runs. The plan says how many tracks point to files that are not here. They are imported anyway, ready to be [relocated](relocate.md).

To import only the part you have copied to this computer, add `--find-in`. Tracks whose files are not here are looked for under that folder, and only the ones found are imported:

```sh
djlib import beets ~/Music/.beetslibrary.db --find-in ~/Music/Artists --apply
```

Run it again after copying more. The tracks imported before are recognized.
