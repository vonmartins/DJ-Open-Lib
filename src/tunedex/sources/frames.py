"""Where each field lives in a file's tags, shared by the tag reader and the tag writer.

Per field: the ID3 frames, the Vorbis comment names and the MP4 atoms, in order of
preference. The reader takes the first one present; the writer writes the first one.
"""

ID3, VORBIS, MP4 = 0, 1, 2

SOURCES: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "title": (("TIT2",), ("TITLE",), ("\xa9nam",)),
    "artist": (("TPE1",), ("ARTIST",), ("\xa9ART",)),
    "album": (("TALB",), ("ALBUM",), ("\xa9alb",)),
    "album_artist": (("TPE2",), ("ALBUMARTIST",), ("aART",)),
    "genre": (("TCON",), ("GENRE",), ("\xa9gen",)),
    "year": (("TDRC",), ("DATE", "YEAR"), ("\xa9day",)),
    "track_number": (("TRCK",), ("TRACKNUMBER",), ("trkn",)),
    "disc_number": (("TPOS",), ("DISCNUMBER",), ("disk",)),
    "bpm": (("TBPM",), ("BPM",), ("tmpo",)),
    "key_original": (("TKEY",), ("INITIALKEY", "KEY"), ("----:com.apple.iTunes:initialkey",)),
    "composer": (("TCOM",), ("COMPOSER",), ("\xa9wrt",)),
    "remixer": (("TPE4",), ("REMIXER", "MIXARTIST"), ("----:com.apple.iTunes:REMIXER",)),
    "label": (("TPUB",), ("LABEL", "ORGANIZATION", "PUBLISHER"), ("----:com.apple.iTunes:LABEL",)),
    "comment": (("COMM",), ("COMMENT", "DESCRIPTION"), ("\xa9cmt",)),
    "grouping": (("TIT1", "GRP1"), ("GROUPING",), ("\xa9grp",)),
    "lyricist": (("TEXT",), ("LYRICIST",), ("----:com.apple.iTunes:LYRICIST",)),
}

ITUNES_COMMENT = "iTun"
"""Comment frames whose description starts with this hold iTunes data, not comments."""


def is_comment(description: str) -> bool:
    """Whether an ID3 comment frame with this description is a comment people wrote."""
    return not description.startswith(ITUNES_COMMENT)
