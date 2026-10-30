# Environment and home

## The home directory

djlib keeps everything it owns in one directory, its **home**:

| Path | What it holds |
|---|---|
| `library.db` | The library: tracks, playlists, sources and history. A [SQLite database](../explanation/store.md). |
| `snapshots/` | One folder per target, with a snapshot taken before each apply. See [Snapshots and restore](../guides/snapshots.md). |
| `rules.yaml` | Your [rules](rules.md), if you write one. |
| `cache.db` | Fingerprints and answers from AcoustID and MusicBrainz, so that `enrich` does not ask twice. Safe to delete. |

The home is chosen in this order:

1. `--home PATH`, given before the command: `djlib --home /tmp/try scan ~/Music`.
2. The `DJLIB_HOME` environment variable.
3. The per-OS default:

| OS | Default home |
|---|---|
| Linux | `$XDG_DATA_HOME/djlib`, else `~/.local/share/djlib` |
| macOS | `~/Library/Application Support/djlib` |
| Windows | `%LOCALAPPDATA%\djlib` |

Nothing is created until a plan is applied. Planning in a home that does not exist works on an empty library and leaves the disk untouched.

A scratch home is the easiest way to try djlib without touching your real library:

```sh
export DJLIB_HOME=/tmp/djlib-try
djlib scan ~/Music --apply
```

## Environment variables

| Variable | Effect |
|---|---|
| `DJLIB_HOME` | The home directory, when `--home` is not given. |
| `DJLIB_ACOUSTID_KEY` | The AcoustID application key `enrich` uses, instead of djlib's own. |
| `NO_COLOR` | Any non-empty value turns color off. Same as `--no-color`. |
| `FORCE_COLOR` | Any non-empty value turns color on even when the output is not a terminal. `NO_COLOR` and `--no-color` win over it. |

Color and progress never appear in `--json` output.
