# djlib

A free, local-first, scriptable DJ library manager.

Your music folder (and optionally your [beets](https://beets.io) library) is the
source of truth. DJ apps such as Traktor, Rekordbox or Mixxx are targets you sync
to safely: every write is planned first, shown as a diff, and backed by a snapshot
you can restore.

> **Status: pre-alpha.** Only folder scans, Mixxx imports, M3U exports and snapshots
> work so far.
> Do not point it at your real DJ library. `djlib` is a working name; the final
> project name is still open.

## Goals

- **Never break your library.** Imports are read-only. Writes need a plan, a
  snapshot and your confirmation. Dry-run is the default.
- **Library as code.** Cleanup rules, smartlists and field mappings live in YAML
  you can version with git.
- **Open data.** A documented SQLite database. No accounts, no telemetry, no cloud.
- **Headless first.** Everything works from the command line, with JSON output.
- **Runs everywhere**, including Linux.

## Trying it out

Every command that writes prints its plan and writes nothing unless you add
`--apply`, which then asks for confirmation (`--yes` skips the question). Add
`--json` for machine-readable output.

```sh
# Use a scratch home instead of your user data directory (or set DJLIB_HOME).
uv run djlib --home /tmp/djlib-try scan ~/Music          # show what would be added
uv run djlib --home /tmp/djlib-try scan ~/Music --apply  # apply it, after confirming

uv run djlib --home /tmp/djlib-try export m3u /tmp/playlists --apply
uv run djlib --home /tmp/djlib-try export m3u /tmp/playlists --playlist Techno/Peak
uv run djlib --home /tmp/djlib-try export m3u /tmp/playlists --modified

uv run djlib --home /tmp/djlib-try snapshot list
uv run djlib --home /tmp/djlib-try snapshot restore <target> <id>
```

- The home directory holds `library.db` and `snapshots/`. By default it is
  `~/.local/share/djlib` on Linux, `~/Library/Application Support/djlib` on macOS
  and `%LOCALAPPDATA%\djlib` on Windows.
- Scans never modify your audio files. Every apply takes a snapshot first, and a
  failed apply puts the target back as it was.
- Exports never delete anything: playlists that exist only in the target are left
  alone and reported. There is no full sync (mirroring) mode.
- `--modified` exports the playlists changed since the last export to the same
  directory. Changing path mappings needs a normal (full) export.

### Importing from Mixxx

```sh
uv run djlib --home /tmp/djlib-try import mixxx            # Mixxx's own library, read only
uv run djlib --home /tmp/djlib-try import mixxx ~/mixxx-test/mixxxdb.sqlite --apply
```

- Mixxx's database is only read (from a consistent copy, even while Mixxx runs). Tracks,
  keys, hot cues, the main cue, loops, beat grids, playlists and crates are imported;
  the Auto DJ queue and the history are not.
- Tracks are matched by path. The first import only fills fields that are empty in
  djlib; later imports take changes made in Mixxx unless you edited the same field in
  djlib too, in which case djlib keeps your value and the plan reports a conflict.
- Playlists and crates go to a `Mixxx` folder (`Mixxx/Playlists`, `Mixxx/Crates`)
  that each import replaces; nothing else in djlib is touched.
- To experiment without your real library, start Mixxx with a separate profile:
  `mixxx --settingsPath ~/mixxx-test`.

### Importing from beets

```sh
uv run djlib --home /tmp/djlib-try import beets                          # beets' own library
uv run djlib --home /tmp/djlib-try import beets ~/Music/.beets.db --apply
```

- beets' database and your music files are only read; beets does not need to be
  installed. Every track is imported with its tags (genre, label, key, MusicBrainz and
  Discogs ids, ISRC…); albums do not become playlists.
- Tracks are matched by path the first time, and to the same beets item afterwards, so a
  track whose path you fix in djlib stays linked. Fields edited in djlib win over later
  beets changes, with a conflict in the plan.
- Without a path, djlib looks where beets does: `$BEETSDIR`, then the `library` setting
  of beets' `config.yaml`, then `~/.config/beets/library.db`. Newer beets versions store
  paths relative to the music directory; it comes from `directory` in the same file, or
  `--music-dir`.
- If beets runs on another computer (a server, a NAS), its paths may not exist where
  djlib runs. The plan says how many tracks point to files that are not here; they are
  imported anyway, to be relocated (see below).
- To bring in only the part of a library you have copied to this computer, add
  `--find-in FOLDER` (also on `import mixxx`): tracks whose files are not here are looked
  for in that folder the way `relocate` does, and only the found ones are imported. Run
  it again after copying more; the tracks imported before are recognised.

  ```sh
  uv run djlib --home /tmp/djlib-try import beets ~/Music/.beetslibrary.db --find-in ~/Music/Artists
  ```

### Relocating tracks

```sh
uv run djlib --home /tmp/djlib-try relocate ~/Elements/Music          # show the plan
uv run djlib --home /tmp/djlib-try relocate ~/Elements/Music --apply
```

- For tracks whose files do not exist on this computer (a disk mounted elsewhere, a
  library made on another machine, a renamed folder), djlib looks for the files under
  the folder you name, by file name, and plans their new paths. There is nothing to
  configure, and it is done once.
- When several files have the same name, the one in the same folders as before wins.
  If that does not settle it, the track is left alone and the plan says so. A file
  already used by another track is never taken.
- Only the path changes: cues, playlists and tags stay, and later imports from the same
  beets or Mixxx library keep matching the track. Files on disk are not touched.
- Walking a large or remote folder (sshfs, NAS) can take a while; `relocate`, `scan`
  and `--find-in` show how many files they have seen so far.

### Enriching tags

```sh
uv run djlib --home /tmp/djlib-try enrich                    # show what would change
uv run djlib --home /tmp/djlib-try enrich --under ~/Music/New --apply
```

`djlib enrich` recognizes each track by its sound and takes its tags from
[MusicBrainz](https://musicbrainz.org). It needs `fpcalc` from Chromaprint
(Arch: `pacman -S chromaprint`; Debian/Ubuntu: `apt install libchromaprint-tools`;
macOS: `brew install chromaprint`; Windows: download it from
[acoustid.org/chromaprint](https://acoustid.org/chromaprint)).

- **What is sent:** the fingerprint of the first two minutes of each file and its
  length go to [AcoustID](https://acoustid.org); the recognized recording and release
  ids go to MusicBrainz. No file names, paths or tags are sent. This is the only
  command that uses the network, and only when you run it.
- **What changes:** the first time a track is enriched, it takes MusicBrainz's title,
  artist, remixer, album, album artist, year, release date, label, and track and disc
  numbers, so names are spelled the same across your library. The genre is filled only
  when empty. MusicBrainz ids, the ISRC and the catalogue number are kept with the
  track. Every change is shown in the plan, marked `(musicbrainz)`.
- **Later runs:** fields you edit in djlib are kept; when both you and MusicBrainz
  changed a field, your value stays and the plan lists the conflict.
- **No guessing:** tracks with several possible recordings, recognized but not in
  MusicBrainz, not recognized, or whose MusicBrainz id (from beets) points elsewhere,
  are left unchanged and listed in the plan's warnings.
- **Speed and cache:** MusicBrainz allows one request per second, so a first run takes
  about two seconds per track. Fingerprints and answers are cached in `cache.db` in the
  djlib home, so later runs are quick and work offline; `--refresh` asks again.

Set `DJLIB_ACOUSTID_KEY` to use your own AcoustID application key.

### Cleaning tags

```sh
uv run djlib --home /tmp/djlib-try fix                       # show what would change
uv run djlib --home /tmp/djlib-try fix --apply
uv run djlib --home /tmp/djlib-try fix --only remove_urls,extract_featured
```

Every change in the plan says which fix or rule made it. Only djlib's library changes;
audio files are never touched, and later scans and imports keep your fixed values.

| Fix | What it does | On by default |
|---|---|---|
| `title_from_file_name` | fills a missing title (and artist) from `Artist - Title.mp3` | yes |
| `fix_encoding` | repairs `CafÃ©` → `Café` and `&amp;` → `&` | yes |
| `normalize_characters` | full-width `：` → `:` (outside CJK text), odd and repeated spaces | yes |
| `remove_urls` | `Glue (freebeats.com)` → `Glue`, also `http…` and `www.…` | yes |
| `remove_video_ids` | `Glue [dOFq-swCWro]` → `Glue` | yes |
| `underscores_to_spaces` | `Sunrise_Overlook_320` → `Sunrise Overlook 320` | yes |
| `remove_leading_number` | `03 - Glue` → `Glue` | yes |
| `extract_featured` | `Storm (feat. Mira)` → title `Storm`, artist `… feat. Mira` | yes |
| `extract_remixer` | fills the remixer from `(Tom Ray Remix)`, title unchanged | yes |
| `fix_case` | `whisper of the trees` → `Whisper of the Trees` | no: one-case titles are often deliberate (`HUMBLE.`, `bad guy`) |

Put a `rules.yaml` in the djlib home (or pass `--rules FILE`) to tune fixes and add
your own rules:

```yaml
fixes:
  extract_featured: false        # keep guests in titles
  fix_case:                      # enable, with names to keep as written
    keep: [DJ, MC, SBTRKT]
rules:
  - id: no-year-in-title
    when: {field: title, op: matches, value: ' \[\d{4}\]$'}
    then: {replace: title, pattern: ' \[\d{4}\]$', with: ''}
  - id: one-dnb-genre
    match: any
    when:
      - {field: genre, op: equals, value: DnB}
      - {field: genre, op: equals, value: Drum n Bass}
    then: {set: genre, value: Drum And Bass}
```

Conditions take a `field` (any track field, such as `title`, `bpm`, `key`, `date_added`
or `tags`), an `op` and a `value` (or `values`):

- text: `equals`, `not_equals`, `contains`, `not_contains`, `starts_with`, `ends_with`,
  `in`, `matches` (a regular expression); case is ignored except by `matches`;
- numbers and dates: `equals`, `not_equals`, `gt`, `gte`, `lt`, `lte`, `in`;
- anything: `empty`, `not_empty`.

### Exporting to Mixxx

Quit Mixxx first: djlib refuses to write while Mixxx runs.

```sh
uv run djlib --home /tmp/djlib-try export mixxx ~/mixxx-test             # show the plan
uv run djlib --home /tmp/djlib-try export mixxx ~/mixxx-test --apply
uv run djlib --home /tmp/djlib-try export mixxx ~/mixxx-test --playlist Techno/Peak
```

- Written: track metadata, BPM and key, hot cues, the main cue, loops, beat grids,
  tracks Mixxx does not have yet, playlists and crates. Everything else in the database
  (analysis data, cover art, ReplayGain, Auto DJ, history) is kept as it is.
- Playlists from the `Mixxx` folder go back to the playlist or crate they came from.
  Other playlists become Mixxx playlists named after their path: `Techno/Peak` is
  written as `Techno / Peak`, and is not imported back as a copy.
- A field edited in Mixxx since the last import is left as Mixxx has it and the plan
  shows a conflict; import first to bring the Mixxx value into djlib.
- Nothing is deleted from Mixxx, and tracks removed from the Mixxx library are not
  brought back. Smartlists, tags and extra memory cues cannot be stored and are listed
  as losses.
- The previous database is kept as a snapshot: `djlib snapshot list` and
  `djlib snapshot restore <target> <id>` put it back (with Mixxx closed).

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run djlib --help
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full set of checks and conventions.

## License

[GPL-3.0-or-later](LICENSE).
