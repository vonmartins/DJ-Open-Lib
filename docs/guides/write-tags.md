# Writing tags to your files

`fix`, `enrich` and the imports clean the **library**. Your audio files keep their old tags until you write them back. CDJs reading a USB stick, other DJ apps and your file manager only see what is in the files, so `write-tags` puts the library's values into them.

```sh
tunedex fix --apply                         # clean the library first
tunedex write-tags --under ~/Music/new      # show what each file would get
tunedex write-tags --under ~/Music/new --apply
```

## The plan

The plan lists every file whose tags differ from the library, with each field's value in the file now and the value it gets:

```text
write tags under /home/ana/Music/new
Files to write: 2 (the tag snapshot takes about 96 kB)
  ~ Sam Paganini - Galaxy  /home/ana/Music/new/galaxy.mp3
      title: 'Galaxy [www.slider.kz]' → 'Galaxy'
      comment: '00000EC8 00000EC8' → —
  ~ Bicep - Glue  /home/ana/Music/new/glue.flac
      artist: 'bicep' → 'Bicep'
Dry run: nothing was written. Run again with --apply to apply it.
```

Only fields that differ are written. A field the library has empty, shown as `—`, is removed from the file.

## What is written

- **Fields:** title, artist, album, album artist, genre, year, track and disc number, BPM, key, composer, remixer, label, comment, grouping and lyricist.
- **Not written:** cues, beat grids, ratings, colors and playlists. They belong to DJ apps and travel with an export.
- **Formats:**
    - **MP3** files get ID3v2.3, the version CDJs, Rekordbox, Serato, Traktor and Windows read best. An ID3v1 tag is updated when the file has one, never added.
    - **FLAC** files get Vorbis comments.
    - **WAV and AIFF** files get their ID3 chunk.
    - **M4A and OGG** files are not written yet. The plan lists them in a warning.
- **Formats of values:** BPM is a whole number when it has no fraction, else up to two decimals. Track and disc numbers keep an existing total, such as `4/12`. The key keeps the text the file had when it means the same key, and is written as `Am` or `F#` otherwise.

## What is kept

Everything else in the file stays as it is: cover art, MusicBrainz ids, ReplayGain, iTunes data and any tag tunedex does not know. The audio is never touched. Each file is written to a temporary copy next to it, the copy's audio is checked against the original's, and only then does the copy replace the file.

One thing can be lost. A few frames exist only in ID3v2.4, such as the sort names `TSOP` and `TSOA` and the mood `TMOO`, and ID3v2.3 cannot hold them. When a file has one, the plan warns before you apply.

## Files that are skipped

- **Files changed since the last scan.** If a file's size or modification time differs from what the last scan saw, another program may have edited its tags. tunedex will not overwrite them blindly: scan the folder first, then write.
- **Missing files**, and tracks that were imported but never scanned.
- **Files whose layout tunedex does not recognize**, such as an MP3 file with unknown data before the audio. They are named in a warning, never guessed at.

## Undo

Before writing, tunedex takes a snapshot of the target `tags`. It holds every byte of each file outside its audio stream, plus a hash of the audio. That is kilobytes per file plus the cover art, never the audio itself, and the plan states the size before you apply.

```sh
tunedex snapshot list tags
tunedex snapshot restore tags 000001-20261031T101500Z --apply
```

The restore rebuilds each file byte for byte as it was. It first checks that each file is still there with the same audio. If one was deleted or replaced by another encoding, nothing is restored and the error names the file.

If writing fails halfway, the files already written are put back at once and the command fails, naming the file.

## Afterwards

The library records each written file's new size and modification time, so the next scan finds nothing to do. The modification time is the time of the write, which is how other programs notice that a file changed and read its tags again.
