# Tutorial

In this tutorial you will scan a music folder, clean its tags and export it to Mixxx, without touching your real library. It takes about ten minutes.

You need djlib [installed](install.md), a folder with some music, and optionally [Mixxx](https://mixxx.org) for the last steps.

## 1. Use a scratch home

djlib keeps its library in a [home directory](reference/environment.md#the-home-directory). For this tutorial, use a scratch one, so that you can delete it afterwards:

```sh
export DJLIB_HOME=/tmp/djlib-try
```

On Windows PowerShell, use `$env:DJLIB_HOME = "$env:TEMP\djlib-try"`.

## 2. Scan your music

```sh
djlib scan ~/Music
```

djlib reads the tags of every audio file and prints its **plan**, the changes it would make:

```text
scan ~/Music
Tracks: 44 added
  + Alley Cat - Mary in the Mirror.mp3  ~/Music/Alley Cat - Mary in the Mirror.mp3
  + Benga - E Trips [6U6S6iXLSmU]  ~/Music/Benga - E Trips.mp3
  …
Dry run: nothing was written. Run again with --apply to apply it.
```

Nothing was written. This is how every command that changes something works: it shows the plan and stops. Your audio files are only read, now and always.

Add `--apply` to carry it out. djlib asks before writing:

```sh
djlib scan ~/Music --apply
```

```text
Applied. Snapshot 000001-20261030T194441Z of library holds the previous state.
```

## 3. Look at the library

```sh
djlib status
djlib list
```

```text
ARTIST      TITLE                           BPM  KEY  TIME  PATH
            Forensix - Solace.mp3                     5:31  Forensix - Solace.mp3
            Formless - Hidden Realm.mp3               4:39  Formless - Hidden Realm.mp3
Benga       E Trips [6U6S6iXLSmU]           140  8m   4:39  Benga - E Trips.mp3
…
44 tracks in ~/Music/
```

Files downloaded from the web often have poor tags: no title, or a video id stuck to it. `djlib show` prints everything djlib knows about one track:

```sh
djlib show "~/Music/Benga - E Trips.mp3"
```

## 4. Clean the tags

```sh
djlib fix
```

```text
fix tags
Tracks: 43 updated
  ~ Alley Cat - Mary in the Mirror.mp3  ~/Music/Alley Cat - Mary in the Mirror.mp3
      title: — → 'Mary in the Mirror'  (title_from_file_name)
  ~ Benga - E Trips [6U6S6iXLSmU]  ~/Music/Benga - E Trips.mp3
      title: 'E Trips [6U6S6iXLSmU]' → 'E Trips'  (remove_video_ids)
  ~ DFRNT - Headspace (Scuba Remix).mp3  ~/Music/DFRNT - Headspace (Scuba Remix).mp3
      title: — → 'Headspace (Scuba Remix)'  (title_from_file_name)
      remixer: — → 'Scuba'  (extract_remixer)
  …
```

Each change says which fix made it. Only djlib's library changes; your files keep their tags. Apply it:

```sh
djlib fix --apply
```

To change what `fix` does, see [fixing tags with rules](guides/fix.md).

## 5. Filter the library

`--where` filters by any field:

```sh
djlib list --where "remixer!="
djlib list --where "bpm>=140"
```

The first lists the tracks that now have a remixer; the second, those at 140 BPM or more.

## 6. Check for duplicates

```sh
djlib dupes
```

If you have two copies of a song, djlib lists them and suggests which one to keep. [Merging duplicates](guides/duplicates.md) explains the rest.

## 7. Export to Mixxx

Do not use your real Mixxx library for this. Start Mixxx once with a separate test profile, then quit it:

```sh
mixxx --settingsPath ~/mixxx-test
```

Now export to that profile:

```sh
djlib export mixxx ~/mixxx-test
```

```text
export mixxx to ~/mixxx-test/mixxxdb.sqlite
Tracks: 44 added
  + Alley Cat - Mary in the Mirror  ~/Music/Alley Cat - Mary in the Mirror.mp3
  …
Losses: 2
  - remixer is not stored: 8 (e.g. DFRNT - Headspace (Scuba Remix), …)
  - date_modified is not stored: 44 (e.g. Alley Cat - Mary in the Mirror, …)
Dry run: nothing was written. Run again with --apply to apply it.
```

**Losses** are what Mixxx cannot keep. djlib tells you before writing; see [adapters and losses](explanation/adapters.md).

```sh
djlib export mixxx ~/mixxx-test --apply
```

Start Mixxx with the test profile again: your tracks are there, with the cleaned titles.

## 8. Undo

Every apply took a snapshot first:

```sh
djlib snapshot list
```

```text
TARGET              ID                       TIME                     REASON
library             000002-20261030T194448Z  2026-10-30 19:44:48 UTC  fix tags
library             000001-20261030T194441Z  2026-10-30 19:44:41 UTC  scan ~/Music
mixxx-2af9b1fc0f27  000001-20261030T194540Z  2026-10-30 19:45:40 UTC  export mixxx to ~/mixxx-test/mixxxdb.sqlite
```

To put the library back as it was before `fix`:

```sh
djlib snapshot restore library 000002-20261030T194448Z --apply
```

## Clean up

Delete the scratch home and the test profile:

```sh
rm -rf /tmp/djlib-try ~/mixxx-test
```

## Next

- Use djlib with your real library: unset `DJLIB_HOME` and djlib uses its [default home](reference/environment.md#the-home-directory).
- Bring in what you already have: [import from Mixxx](guides/import-mixxx.md) or [from beets](guides/import-beets.md).
- Fill in missing tags from MusicBrainz with [`enrich`](guides/enrich.md).
