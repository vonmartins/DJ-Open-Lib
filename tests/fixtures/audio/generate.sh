#!/bin/sh
# Regenerates the synthetic test clips: 0.5 s of 8 kHz mono silence per format, without
# tags or encoder strings. Needs ffmpeg and the project environment (uv). The clips are
# committed; tests never run this script.
set -eu
cd "$(dirname "$0")"
input="-y -hide_banner -loglevel error -f lavfi -i anullsrc=r=8000:cl=mono"
output="-t 0.5 -fflags +bitexact -flags:a +bitexact -map_metadata -1"

ffmpeg $input $output -c:a libmp3lame -b:a 8k -id3v2_version 0 -write_id3v1 0 silence.mp3
ffmpeg $input $output -c:a flac silence.flac
ffmpeg $input $output -c:a pcm_s16le silence.wav
ffmpeg $input $output -c:a pcm_s16be -f aiff silence.aiff
ffmpeg $input $output -c:a aac -b:a 16k -f mp4 silence.m4a
ffmpeg $input $output -c:a libvorbis -q:a 0 silence.ogg

# ffmpeg always writes an "encoder" comment into Ogg files; remove every tag.
uv run python -c '
import mutagen, sys
for name in sys.argv[1:]:
    audio = mutagen.File(name)
    if audio.tags:
        audio.delete()
' silence.ogg silence.flac silence.m4a

# Tagged clips: ID3v2.4 with art and MusicBrainz ids, ID3v2.3 with ID3v1, APEv2, FLAC
# with a picture, ID3 chunks in WAV and AIFF, and an M4A file.
uv run python tagged.py .
