# Using tunedex from another program

A TUI, a desktop app, a web front end or a script can build on tunedex in two ways:

- **From any language**, run the `tunedex` commands with `--json` and read their output.
- **From Python**, import `tunedex` and call its [API](../reference/python-api.md).

Both give the same guarantees as the command line: nothing is written without a plan, a snapshot and a confirmation.

## With `--json`

Every command accepts `--json`. Standard output then holds exactly one JSON document, whose `format` and `version` name its shape. The [JSON formats](../reference/json.md) reference describes each one.

```console
$ tunedex list --where "bpm>=170" --json
{
  "format": "tunedex-tracks",
  "version": 1,
  "tracks": [ ... ]
}
```

- Check `format` and `version` before reading a document. A new version means an incompatible change; new fields can appear at any time.
- Questions and progress go to standard error, never to standard output.
- The [exit code](../reference/errors.md#exit-codes) is 0 on success, 1 on an expected error and 2 on wrong usage.
- An expected error is a JSON document on standard error, with a stable [`code`](../reference/errors.md#error-codes):

```json
{"error": {"code": "unknown_playlist", "message": "no playlist or folder at 'Nope'"}}
```

### Showing a plan and applying it

A client applies a plan its user confirmed in two steps:

1. Run the command without `--apply`. You get the plan as a [`tunedex-plan`](../reference/json.md#tunedex-plan) document, and nothing is written. Show it to the user.
2. If the user accepts, run the same command with `--apply --yes`. The document now also has a `result`.

```sh
tunedex fix --json                  # 1. the plan, to show
tunedex fix --apply --yes --json    # 2. after the user accepts
```

The second run makes the plan again from the current state and applies that one, so its document shows what was actually applied. If the library or the target changes while it runs, it fails with `stale_target` and writes nothing.

Without `--yes`, a command that would ask for confirmation fails with `needs_yes` when standard input is not a terminal. A client therefore never hangs on a question.

### Merging duplicates without questions

`tunedex dupes --merge` asks about each group in a terminal. A client gives every answer as an option instead:

```sh
tunedex dupes --json                                     # the groups, to show
tunedex dupes --merge --keep ~/Music/a.flac --skip ~/Music/c.mp3 --ignore ~/Music/e.mp3 --json
tunedex dupes --merge --keep ~/Music/a.flac --skip ~/Music/c.mp3 --ignore ~/Music/e.mp3 --apply --yes --json
```

`--keep PATH` keeps that track in its group, `--skip PATH` leaves its group unmerged, and `--ignore PATH` marks its group as not duplicates. Groups without an answer take the suggested track.

### Using the right library

Pass `--home PATH` before the command, or set `TUNEDEX_HOME`, to choose the [home](../reference/environment.md). Without either, tunedex uses the user's default home, the same one the user's own `tunedex` commands use.

## From Python

Import `tunedex`. The names it exports are the stable API; every other module is internal.

```python
import tunedex

home = tunedex.Home(tunedex.resolve_home())  # the home of the command line, or pass a path

with home.engine() as engine:
    # Browse
    for track in tunedex.select(engine.store, where=[tunedex.parse_where("bpm>=170")]):
        print(track.artist, track.title, track.bpm)

    # Plan, show, apply
    plan = engine.plan_scan("/path/to/music")
    print(tunedex.render_text(plan))
    result = home.apply(engine, plan, confirm=tunedex.assume_yes)
    print(result.status, result.snapshot)
```

- `resolve_home()` picks the home the way the command line does: the given path, then `TUNEDEX_HOME`, then the default.
- Planning never writes. In a home without a library, the engine plans on an empty library in memory, and `home.apply` creates the library when it applies. For browsing only, `tunedex.open_library()` is a shortcut for `Home(resolve_home()).engine()`.
- `confirm` is called with the plan and returns whether to go ahead, so an app can ask its user there. `assume_yes` accepts every plan.
- `to_json(plan, result)` gives the same document as `--json`.
- A plan can be applied later, after the user has looked at it. If the library or the target changed since the plan was made, applying raises `StaleTargetError` and writes nothing: make the plan again.
- Errors are the exception classes listed in the [API reference](../reference/python-api.md#errors).
- Importing `tunedex` does not load the command-line layer, so it is cheap to embed.
