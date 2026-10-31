"""``tunedex snapshot``: list snapshots and restore one."""

import json
from typing import Annotated

import typer

from tunedex.cli import _console, _options
from tunedex.cli._flow import confirm, home_of, reported_errors, stdin_is_interactive
from tunedex.model.unmapped import JSONValue
from tunedex.snapshots import Snapshot

app = typer.Typer(
    rich_markup_mode="markdown", help="List and restore snapshots.", no_args_is_help=True
)

SNAPSHOTS_FORMAT = "tunedex-snapshots"
RESTORE_FORMAT = "tunedex-restore"


@app.command("list")
def list_snapshots(
    ctx: typer.Context,
    target: Annotated[str | None, typer.Argument(help="Only this target, such as library.")] = None,
    as_json: _options.Json = False,
    _no_color: _options.NoColor = False,
) -> None:
    """List snapshots, newest first, with their target, id, time and reason.

    Example: tunedex snapshot list library
    """
    with reported_errors(as_json):
        store = home_of(ctx).snapshots
        targets = [target] if target else store.targets()
        snapshots = [s for name in targets for s in store.list(name)]
    if as_json:
        document: dict[str, JSONValue] = {
            "format": SNAPSHOTS_FORMAT,
            "version": 1,
            "snapshots": [_snapshot_json(s) for s in snapshots],
        }
        typer.echo(json.dumps(document, ensure_ascii=False, indent=2))
        return
    if not snapshots:
        _console.echo("No snapshots.")
        return
    rows = [
        (s.target, s.id, s.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"), s.reason or "")
        for s in snapshots
    ]
    lines = _console.columns([("TARGET", "ID", "TIME", "REASON"), *rows])
    _console.echo_lines([(lines[0], "header"), *((line, None) for line in lines[1:])])


@app.command("restore")
def restore(
    ctx: typer.Context,
    target: Annotated[
        str,
        typer.Argument(help="Target name, as shown by tunedex snapshot list.", show_default=False),
    ],
    snapshot_id: Annotated[
        str, typer.Argument(metavar="ID", help="Snapshot identifier.", show_default=False)
    ],
    apply: Annotated[
        bool, typer.Option("--apply", help="Restore the snapshot (asks for confirmation).")
    ] = False,
    yes: _options.Yes = False,
    as_json: _options.Json = False,
    _no_color: _options.NoColor = False,
) -> None:
    """Put the files of a target back as they were in a snapshot.

    Shows the files it would put back or remove; --apply restores them. The current
    state is saved in a new snapshot first, so a restore can be undone.

    Example: tunedex snapshot restore library 000012-20261029T120000Z --apply
    """
    with reported_errors(as_json):
        store = home_of(ctx).snapshots
        snapshot = store.get(target, snapshot_id)
        if not as_json:
            reason = snapshot.reason or "no reason"
            heading = f"Restore {target} to snapshot {snapshot.id} ({reason}):"
            _console.echo_lines(
                [
                    (heading, "heading"),
                    *(
                        (f"  put back {r.path}", "updated")
                        if r.present
                        else (f"  remove {r.path}", "removed")
                        for r in snapshot.files
                    ),
                ]
            )
        result: dict[str, JSONValue] | None = None
        if apply:
            if as_json and not (yes or stdin_is_interactive()):
                typer.echo(json.dumps(_restore_json(snapshot), ensure_ascii=False, indent=2))
            if confirm("Restore this snapshot?", yes=yes, as_json=as_json, refused="not restored"):
                restored = store.restore(snapshot)
                result = {"status": "restored", "pre_restore": restored.pre_restore.id}
            else:
                result = {"status": "declined"}
    if as_json:
        typer.echo(json.dumps(_restore_json(snapshot, result), ensure_ascii=False, indent=2))
    elif result is None:
        _console.echo(
            "Dry run: nothing was restored. Run again with --apply to restore it.", "notice"
        )
    elif result["status"] == "declined":
        _console.echo("Not restored.", "notice")
    else:
        _console.echo(
            f"Restored. Snapshot {result['pre_restore']} holds the state from just before"
            " the restore.",
            "added",
        )


def _restore_json(
    snapshot: Snapshot, result: dict[str, JSONValue] | None = None
) -> dict[str, JSONValue]:
    document: dict[str, JSONValue] = {
        "format": RESTORE_FORMAT,
        "version": 1,
        "target": snapshot.target,
        "snapshot": snapshot.id,
        "files": [
            {"path": r.path, "action": "put_back" if r.present else "remove"}
            for r in snapshot.files
        ],
    }
    if result is not None:
        document["result"] = result
    return document


def _snapshot_json(snapshot: Snapshot) -> dict[str, JSONValue]:
    return {
        "target": snapshot.target,
        "id": snapshot.id,
        "created_at": snapshot.created_at.isoformat(),
        "reason": snapshot.reason,
        "tunedex_version": snapshot.tunedex_version,
        "files": [r.path for r in snapshot.files],
    }
