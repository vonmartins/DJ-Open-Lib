"""Tagged copies of the synthetic audio clips, written with mutagen.

This mapping is written independently of tunedex's tag reader on purpose, so tests do not
check the reader against itself.
"""

import shutil
from pathlib import Path

import mutagen
from mutagen import id3
from mutagen.mp4 import MP4, MP4FreeForm

CLIPS = Path(__file__).parents[1] / "fixtures" / "audio"
FORMATS = ("mp3", "flac", "wav", "aiff", "m4a", "ogg")

# field -> (ID3 frame, Vorbis comment, MP4 atom)
_KEYS: dict[str, tuple[str, str, str]] = {
    "title": ("TIT2", "TITLE", "\xa9nam"),
    "artist": ("TPE1", "ARTIST", "\xa9ART"),
    "album": ("TALB", "ALBUM", "\xa9alb"),
    "album_artist": ("TPE2", "ALBUMARTIST", "aART"),
    "genre": ("TCON", "GENRE", "\xa9gen"),
    "date": ("TDRC", "DATE", "\xa9day"),
    "track": ("TRCK", "TRACKNUMBER", "trkn"),
    "disc": ("TPOS", "DISCNUMBER", "disk"),
    "bpm": ("TBPM", "BPM", "tmpo"),
    "key": ("TKEY", "INITIALKEY", "----:com.apple.iTunes:initialkey"),
    "composer": ("TCOM", "COMPOSER", "\xa9wrt"),
    "remixer": ("TPE4", "REMIXER", "----:com.apple.iTunes:REMIXER"),
    "label": ("TPUB", "LABEL", "----:com.apple.iTunes:LABEL"),
    "comment": ("COMM", "COMMENT", "\xa9cmt"),
    "grouping": ("TIT1", "GROUPING", "\xa9grp"),
    "lyricist": ("TEXT", "LYRICIST", "----:com.apple.iTunes:LYRICIST"),
}


def tagged_copy(directory: Path, fmt: str, name: str | None = None, **tags: str) -> Path:
    """Copy the ``fmt`` clip to ``directory / name`` and write ``tags`` (field=value)."""
    target = directory / (name or f"track.{fmt}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CLIPS / f"silence.{fmt}", target)
    if tags:
        write_tags(target, **tags)
    return target


def write_tags(path: Path, **tags: str) -> None:
    audio = mutagen.File(path)
    assert audio is not None, path
    if isinstance(audio, MP4):
        _write_mp4(audio, tags)
    elif path.suffix in (".flac", ".ogg"):
        for field, value in tags.items():
            audio[_KEYS[field][1]] = value
    else:
        if audio.tags is None:
            audio.add_tags()
        frames = audio.tags
        assert frames is not None
        for field, value in tags.items():
            frame = _KEYS[field][0]
            if frame == "COMM":
                frames.add(id3.COMM(encoding=3, lang="eng", desc="", text=value))
            else:
                frames.add(getattr(id3, frame)(encoding=3, text=value))
    audio.save()


def _write_mp4(audio: MP4, tags: dict[str, str]) -> None:
    for field, value in tags.items():
        atom = _KEYS[field][2]
        if atom in ("trkn", "disk"):
            number, _, total = value.partition("/")
            audio[atom] = [(int(number), int(total or 0))]
        elif atom == "tmpo":
            audio[atom] = [int(float(value))]
        elif atom.startswith("----:"):
            audio[atom] = [MP4FreeForm(value.encode("utf-8"))]
        else:
            audio[atom] = [value]
