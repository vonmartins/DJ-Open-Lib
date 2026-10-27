"""``djlib snapshot``: list snapshots and restore one."""

import json
from typing import Annotated

import typer

from djlib.cli import _options
from djlib.cli._flow import fail, home_of, reported_errors, stdin_is_interactive
from djlib.model.unmapped import JSONValue
from djlib.snapshots import Snapshot

app = typer.Typer(help="List and restore snapshots.", no_args_is_help=True)

SNAPSHOTS_FORMAT = "djlib-snapshots"


@app.command("list")
def list_snapshots(
    ctx: typer.Context,
    target: Annotated[str | None, typer.Argument(help="Only this target, such as library.")] = None,
    as_json: _options.Json = False,
) -> None:
    """List snapshots, newest first."""
    with reported_errors():
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
        typer.echo("No snapshots.")
        return
    for snapshot in snapshots:
        created = snapshot.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        typer.echo(f"{snapshot.target}  {snapshot.id}  {created}  {snapshot.reason or ''}".rstrip())


@app.command("restore")
def restore(
    ctx: typer.Context,
    target: Annotated[str, typer.Argument(help="Target name, as shown by `djlib snapshot list`.")],
    snapshot_id: Annotated[str, typer.Argument(metavar="ID", help="Snapshot identifier.")],
    yes: _options.Yes = False,
) -> None:
    """Put the files of TARGET back as they were in snapshot ID."""
    with reported_errors():
        store = home_of(ctx).snapshots
        snapshot = store.get(target, snapshot_id)
        typer.echo(
            f"Restore {target} to snapshot {snapshot.id} ({snapshot.reason or 'no reason'}):"
        )
        for record in snapshot.files:
            typer.echo(f"  {'put back' if record.present else 'remove'} {record.path}")
        if not yes:
            if not stdin_is_interactive():
                fail("not restored: confirmation needs an interactive terminal; pass --yes")
            if not typer.confirm("Restore this snapshot?", default=False):
                typer.echo("Not restored.")
                return
        result = store.restore(snapshot)
    typer.echo(
        f"Restored. Snapshot {result.pre_restore.id} holds the state from just before the restore."
    )


def _snapshot_json(snapshot: Snapshot) -> dict[str, JSONValue]:
    return {
        "target": snapshot.target,
        "id": snapshot.id,
        "created_at": snapshot.created_at.isoformat(),
        "reason": snapshot.reason,
        "djlib_version": snapshot.djlib_version,
        "files": [r.path for r in snapshot.files],
    }
