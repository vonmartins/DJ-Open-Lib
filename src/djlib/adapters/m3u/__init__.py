"""M3U and M3U8 playlists.

Supported: playlists, folders (as directories), entry order with repeats, and the
track fields artist, title and duration (via ``#EXTINF``). Reading accepts a single
file or a directory tree, relative and absolute entries and ``file://`` URIs; other
URLs are skipped with a warning. Unknown directives are kept and written back while
the entry they precede is unchanged.

Writing produces one UTF-8 ``.m3u8`` file per playlist with absolute paths (or paths
relative to each file with ``relative_paths=True``), names made valid on every OS.

Lost on write, and reported in the plan: smartlists (not written), cues, beatgrids,
tags, every other track field, sub-second durations, tracks in no written playlist,
and data kept from other formats.
"""

from djlib.adapters.m3u.adapter import M3UAdapter

__all__ = ["M3UAdapter"]
