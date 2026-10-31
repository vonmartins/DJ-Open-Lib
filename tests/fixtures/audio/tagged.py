"""Writes the tagged clips from the silent ones, with mutagen. Run by ``generate.sh``.

Each clip carries the kinds of tags found in real collections: an ID3v2.4 tag with
cover art and MusicBrainz ids, ID3v2.3 with ID3v1, an APEv2 tag, a FLAC picture, and
ID3 chunks in WAV and AIFF files. The values are made up.
"""

import shutil
import struct
import sys
import zlib
from pathlib import Path

from mutagen import id3
from mutagen.aiff import AIFF
from mutagen.apev2 import APEv2
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

RECORDING_ID = "6340a9b8-f427-4d89-a842-971a52ad3ce4"


def png() -> bytes:
    """A 16x16 grey PNG image, as small cover art."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + b"\x80" * 16 for _ in range(16))
    header = struct.pack(">IIBBBBB", 16, 16, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def id3_frames(tags: id3.ID3) -> None:
    tags.add(id3.TIT2(encoding=3, text="Galaxy [www.slider.kz]"))
    tags.add(id3.TPE1(encoding=3, text="Sam Paganini"))
    tags.add(id3.TALB(encoding=3, text="Galaxy EP"))
    tags.add(id3.TDRC(encoding=3, text="2012-05-01"))
    tags.add(id3.TRCK(encoding=3, text="3/12"))
    tags.add(id3.TBPM(encoding=3, text="128"))
    tags.add(id3.TKEY(encoding=3, text="8m"))
    tags.add(id3.COMM(encoding=3, lang="eng", desc="", text="first release"))
    tags.add(id3.COMM(encoding=0, lang="eng", desc="iTunNORM", text=" 00000EC8 00000EC8"))
    tags.add(id3.APIC(encoding=3, mime="image/png", type=3, desc="", data=png()))
    tags.add(id3.UFID(owner="http://musicbrainz.org", data=RECORDING_ID.encode()))
    tags.add(id3.TXXX(encoding=3, desc="MusicBrainz Release Track Id", text=RECORDING_ID))


def main(folder: Path) -> None:
    mp3 = folder / "silence.mp3"

    target = folder / "tagged-v24.mp3"
    shutil.copyfile(mp3, target)
    tags = id3.ID3()
    id3_frames(tags)
    tags.add(id3.TSOP(encoding=3, text="Paganini, Sam"))  # ID3v2.4 only
    tags.save(target, v2_version=4, v1=0)

    target = folder / "tagged-v23-v1.mp3"
    shutil.copyfile(mp3, target)
    tags = id3.ID3()
    id3_frames(tags)
    tags.update_to_v23()
    tags.save(target, v2_version=3, v1=2)

    target = folder / "tagged-ape.mp3"
    shutil.copyfile(mp3, target)
    tags = id3.ID3()
    id3_frames(tags)
    tags.update_to_v23()
    tags.save(target, v2_version=3, v1=2)
    ape = APEv2()
    ape["Title"] = "Galaxy (APE)"
    ape["Replaygain_Track_Gain"] = "-6.20 dB"
    ape.save(target)

    target = folder / "tagged.flac"
    shutil.copyfile(folder / "silence.flac", target)
    flac = FLAC(target)
    flac["TITLE"] = "Galaxy [www.slider.kz]"
    flac["ARTIST"] = "Sam Paganini"
    flac["DATE"] = "2012"
    flac["TRACKNUMBER"] = "3/12"
    flac["INITIALKEY"] = "Am"
    flac["MUSICBRAINZ_TRACKID"] = RECORDING_ID
    picture = Picture()
    picture.type, picture.mime, picture.data = 3, "image/png", png()
    picture.width, picture.height, picture.depth = 16, 16, 8
    flac.add_picture(picture)
    flac.save()

    for name in ("wav", "aiff"):
        target = folder / f"tagged.{name}"
        shutil.copyfile(folder / f"silence.{name}", target)
        chunked = WAVE(target) if name == "wav" else AIFF(target)
        chunked.add_tags()
        assert isinstance(chunked.tags, id3.ID3)
        id3_frames(chunked.tags)
        chunked.save(v2_version=3)

    target = folder / "tagged.m4a"
    shutil.copyfile(folder / "silence.m4a", target)
    m4a = MP4(target)
    m4a["\xa9nam"] = ["Galaxy [www.slider.kz]"]
    m4a["\xa9ART"] = ["Sam Paganini"]
    m4a.save()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
