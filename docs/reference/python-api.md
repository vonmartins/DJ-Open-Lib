# Python API

A Python program can use djlib without the command line:

```python
import djlib

with djlib.open_library() as engine:  # the home of the command line, or pass a path
    for track in djlib.select(engine.store, where=[djlib.parse_where("bpm>=170")]):
        print(track.artist, track.title)
    plan = engine.plan_scan("/path/to/music")
    print(djlib.render_text(plan))
```

The names on this page are the API programs may rely on. Every other module is internal and may change in any release. Importing `djlib` does not load the command-line layer.

See [Using djlib from another program](../guides/from-another-program.md) for a walk-through.

## Opening a library

::: djlib.open_library

::: djlib.Home

::: djlib.resolve_home

::: djlib.default_home

## Planning and applying

::: djlib.Engine

::: djlib.Plan

::: djlib.ApplyResult

::: djlib.Confirm

::: djlib.assume_yes

::: djlib.render_text

::: djlib.to_json

## Browsing

::: djlib.select

::: djlib.parse_where

::: djlib.find_track

::: djlib.track_view

::: djlib.TrackView

::: djlib.status

::: djlib.Status

::: djlib.playlist_tree

::: djlib.TreeNode

## Errors

Every expected failure raises one of these. The command line turns them into the [error codes](errors.md).

::: djlib.PlanError

::: djlib.StaleTargetError

::: djlib.ApplyFailedError

::: djlib.UnknownPlaylistError

::: djlib.AdapterError

::: djlib.EnrichError

::: djlib.RuleError

::: djlib.SnapshotError

::: djlib.StoreError
