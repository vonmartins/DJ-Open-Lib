# Enriching tags

`tunedex enrich` recognizes each track by its sound and takes its tags from [MusicBrainz](https://musicbrainz.org). It is the cure for files with poor or missing tags.

```sh
tunedex enrich                              # show what would change
tunedex enrich --under ~/Music/New --apply
```

It needs `fpcalc`; see [install](../install.md#optional-fpcalc-for-enrich).

## What is sent

`enrich` is the only command that uses the network, and only when you run it.

- To [AcoustID](https://acoustid.org): the fingerprint of the first two minutes of each file, and its length.
- To MusicBrainz: the ids of the recognized recordings and releases.

No file names, paths or tags are sent. See [network use](../explanation/network.md).

## What changes

The first time a track is enriched, it takes MusicBrainz's title, artist, remixer, album, album artist, year, release date, label, and track and disc numbers. Names are then spelled the same across your library.

- The genre is filled only when it is empty.
- MusicBrainz ids, the ISRC and the catalogue number are kept with the track.
- Every change is shown in the plan, marked `(musicbrainz)`.

## Later runs

Fields you edit in tunedex are kept. When both you and MusicBrainz changed a field, your value stays and the plan lists the conflict.

## No guessing

These tracks are left unchanged and listed in the plan's warnings:

- tracks with several possible recordings;
- tracks recognized but not in MusicBrainz;
- tracks not recognized;
- tracks whose MusicBrainz id, from beets, points elsewhere;
- tracks whose recording does not fit their own tags. When a track has an artist, in its tags or as `Artist - ` in its file name, the recording's artist must share a word with it; otherwise the title or file name must share a word with the recording's title. This keeps AcoustID's occasional wrong match from replacing good tags. The plan lists the first 20, with what the track says and what AcoustID heard.

Once applied, running it again on an unchanged library just says `Nothing to do.`

## Speed and cache

MusicBrainz allows one request per second, so a first run takes about two seconds per track. A bar shows the progress.

Fingerprints and answers are cached in `cache.db` in the [tunedex home](../reference/environment.md#the-home-directory). Later runs are quick and work offline. `--refresh` asks the services again.

Set `TUNEDEX_ACOUSTID_KEY` to use your own AcoustID application key.
