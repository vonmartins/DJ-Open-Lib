# Network use

tunedex works offline. It has no accounts, no telemetry and no update checks, and it never sends anything anywhere on its own.

## The one exception: `enrich`

[`tunedex enrich`](../guides/enrich.md) is the only command that uses the network, and only when you run it. It talks to two open services:

| Service | What tunedex sends | What it gets back |
|---|---|---|
| [AcoustID](https://acoustid.org) | The audio fingerprint of the first two minutes of each file, and its length | The recordings that sound like it |
| [MusicBrainz](https://musicbrainz.org) | The ids of those recordings and their releases | Titles, artists, labels, dates and ids |

No file names, paths or tags are sent. A fingerprint is a compact summary of the sound: it identifies the recording, not your file.

## Being a good citizen

- MusicBrainz asks for at most one request per second and AcoustID for three. tunedex keeps to both, which is why a first run takes about two seconds per track.
- Answers are cached in `cache.db` in the home, so the same track is never looked up twice unless you pass `--refresh`.
- tunedex identifies itself to AcoustID with its own application key. Set `TUNEDEX_ACOUSTID_KEY` to use yours instead.

## Everything else

Every other command reads and writes only local files: your music, the tunedex home, and the targets you name. The test suite enforces this: the command-line tests block every network connection, and `enrich` is tested against a fake service.
