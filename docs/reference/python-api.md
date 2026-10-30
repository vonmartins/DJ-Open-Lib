# Python API

A Python program can use tunedex without the command line:

```python
import tunedex

with tunedex.open_library() as engine:  # the home of the command line, or pass a path
    for track in tunedex.select(engine.store, where=[tunedex.parse_where("bpm>=170")]):
        print(track.artist, track.title)
    plan = engine.plan_scan("/path/to/music")
    print(tunedex.render_text(plan))
```

The names on this page are the API programs may rely on. Every other module is internal and may change in any release. Importing `tunedex` does not load the command-line layer.

See [Using tunedex from another program](../guides/from-another-program.md) for a walk-through.

## Opening a library

::: tunedex.open_library

::: tunedex.Home

::: tunedex.resolve_home

::: tunedex.default_home

## Planning and applying

::: tunedex.Engine

::: tunedex.Plan

::: tunedex.ApplyResult

::: tunedex.Confirm

::: tunedex.assume_yes

::: tunedex.render_text

::: tunedex.to_json

## Browsing

::: tunedex.select

::: tunedex.parse_where

::: tunedex.find_track

::: tunedex.track_view

::: tunedex.TrackView

::: tunedex.status

::: tunedex.Status

::: tunedex.playlist_tree

::: tunedex.TreeNode

## Errors

Every expected failure raises one of these. The command line turns them into the [error codes](errors.md).

::: tunedex.PlanError

::: tunedex.StaleTargetError

::: tunedex.ApplyFailedError

::: tunedex.UnknownPlaylistError

::: tunedex.AdapterError

::: tunedex.EnrichError

::: tunedex.RuleError

::: tunedex.SnapshotError

::: tunedex.StoreError
