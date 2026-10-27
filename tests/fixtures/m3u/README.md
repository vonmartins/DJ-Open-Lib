# M3U fixtures

All files here are **synthetic**, written by hand for the tests. They contain no
personal data, and the audio paths they list do not exist (the adapter never opens
audio files).

- `tree/`: a playlist folder tree. Includes a hidden directory and a directory
  without playlists, which must both be ignored, and a non-playlist file.
- `single/mixed.m3u8`: CRLF line endings, a byte-order mark, a `file://` URI, a
  stream URL, a float `#EXTINF` duration with attributes, and an `#EXTVLCOPT`
  directive before the second entry.
- `single/legacy.m3u`: Windows-1252 encoded (`é` as byte 0xE9).
- `single/broken.m3u8`: invalid UTF-8; reading it must fail.
