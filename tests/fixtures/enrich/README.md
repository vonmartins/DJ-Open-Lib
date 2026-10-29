# Enrichment fixtures

Real answers from AcoustID (`/v2/lookup`, `meta=recordings`) and MusicBrainz (`/ws/2/recording`, `/ws/2/release`), captured on 2026-10-29 for a few test tracks. They are public catalogue data; no fingerprint or audio is stored here.

| File | Case |
|---|---|
| `acoustid-dfrnt.json` | One recording, score 0.99: `Headspace (Scuba remix)` |
| `acoustid-lung.json` | Two recordings with the same title and nearly the same length (MusicBrainz duplicates) |
| `acoustid-irrelevant.json` | Recognized (score 0.97), but linked to no MusicBrainz recording |
| `acoustid-marina.json` | Not recognized: no results |
| `acoustid-nanobyte.json` | One recording, `Tek-1` (`recording-82eaaf51-…`, on `release-faeabdc0-…`, *Kalyke EP*) |
| `recording-<id>.json` | Recordings with `inc=artist-credits+releases+isrcs+artist-rels+genres` |
| `release-<id>.json` | Releases with `inc=labels+recordings+artist-credits` |

`recording-6340a9b8-…` (`Black Sun Empire feat. Optiv – Insiders`) shows a credit with a join phrase, an ISRC, a genre and producer relations. None of these recordings has a remixer relation: the remixer is only in the title.
