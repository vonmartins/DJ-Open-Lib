# Errors and exit codes

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. This includes a dry run, a declined confirmation and a plan with nothing to do. |
| `1` | An expected error: something the user can act on, such as a missing folder or a target that changed. The message is printed on standard error. |
| `2` | Wrong usage: an unknown option, a missing argument or an invalid value. Typer prints the usage and the problem on standard error. |

Any other code, with a traceback, is a bug. Please [report it](https://github.com/vonmartins/DJ-Open-Lib/issues).

## Error messages

Without `--json`, an expected error is one line on standard error:

```console
$ djlib export m3u /tmp/out --playlist Nope
error: no playlist or folder at 'Nope'
```

With `--json`, standard output stays empty and standard error holds one JSON document:

```json
{"error": {"code": "unknown_playlist", "message": "no playlist or folder at 'Nope'"}}
```

`code` is stable: a client can rely on it. `message` is for people and may change. Usage errors (exit code 2) stay plain text even with `--json`.

## Error codes

| Code | When |
|---|---|
| `invalid_argument` | An argument has a valid form but cannot be used, such as a folder that does not exist or contradictory options. |
| `not_found` | A track, snapshot or file named in the command does not exist. |
| `needs_yes` | A command would ask for confirmation, but standard input is not a terminal. Pass `--yes`. |
| `unknown_playlist` | `--playlist` names no playlist or folder. The message suggests close names. |
| `stale_target` | A file the plan would write changed after the plan was made. Nothing was written; make the plan again. |
| `apply_failed` | Writing failed after it started. See [below](#apply_failed). |
| `not_a_library` | The database in the home is not a djlib library. |
| `library_too_new` | The library was written by a newer djlib. Upgrade djlib. |
| `invalid_rule` | A rule, condition or fix in a rules file or in `--where` is invalid. The message says where. |
| `adapter_error` | A source or target file cannot be read or understood, such as a damaged Mixxx database. |
| `enrich_error` | `enrich` cannot run: `fpcalc` is missing, a service is unreachable, or a service gave a bad answer. |
| `plan_error` | Another planning or applying problem. |
| `snapshot_error` | A snapshot cannot be taken, read or restored. |
| `store_error` | Another problem with the library database. |
| `os_error` | The operating system refused an operation, such as a permission denied or a full disk. |

New codes can be added in any release. A client should handle an unknown code like a generic error.

### `apply_failed`

The error document has three more fields:

```json
{
  "error": {
    "code": "apply_failed",
    "message": "applying failed ([Errno 28] No space left on device); the target was restored to its previous state",
    "target": "m3u-568b52ce5ecb",
    "snapshot": "000004-20261030T201502Z",
    "restored": true
  }
}
```

| Field | Meaning |
|---|---|
| `target` | The [target](json.md#djlib-plan) that was being written. |
| `snapshot` | The snapshot taken before writing. |
| `restored` | `true` when djlib put the target back as it was. `false` when it could not: restore it with `djlib snapshot restore <target> <snapshot> --apply`. |
