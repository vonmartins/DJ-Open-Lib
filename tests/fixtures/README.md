# Test fixtures

Sample libraries used by the test suite, grouped by format and app version
(for example `traktor/pro4/collection.nml`).

## Rules

- **Sanitized only.** Every fixture must be free of personal data: no real
  usernames, home directories, machine names, emails or private file paths.
  Replace them with neutral placeholders such as `/music/Artist/Track.mp3`.
- **Never point tests at real DJ app files.** Tests read fixtures from this
  directory and write only to temporary directories. No test may open the live
  library of Traktor, Rekordbox or any other installed app.
- **Document the origin.** Each fixture directory needs a short note on how it
  was produced (app and version, export steps, what was sanitized).
- **Keep them small.** Use the minimum number of tracks that exercises the
  behavior under test. Audio files, when needed, should be short synthetic clips.
