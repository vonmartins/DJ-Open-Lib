"""The flow every writing command shares: plan, show, confirm, apply, report."""

import contextlib
import contextvars
import json
import sys
from collections.abc import Callable, Generator
from pathlib import Path
from typing import NoReturn

import typer

from djlib.adapters.errors import AdapterError
from djlib.enrich import EnrichError
from djlib.home import Home
from djlib.model.unmapped import JSONValue
from djlib.planning import (
    ApplyFailedError,
    ApplyResult,
    Engine,
    Plan,
    PlanError,
    StaleTargetError,
    UnknownPlaylistError,
    assume_yes,
    render_text,
    to_json,
)
from djlib.rules import RuleError
from djlib.snapshots import SnapshotError
from djlib.store import NotADjlibDatabaseError, NotFoundError, SchemaTooNewError, StoreError

# Failures users can act on: one line on stderr, exit code 1, no traceback.
EXPECTED_ERRORS = (
    AdapterError,
    EnrichError,
    OSError,
    PlanError,
    RuleError,
    SnapshotError,
    StoreError,
)


def home_of(ctx: typer.Context) -> Home:
    home = ctx.find_root().obj
    assert isinstance(home, Home)  # noqa: S101 - set by the root callback
    return home


# Error codes for --json, most specific class first. They are part of the JSON contract.
ERROR_CODES: tuple[tuple[type[Exception], str], ...] = (
    (UnknownPlaylistError, "unknown_playlist"),
    (StaleTargetError, "stale_target"),
    (ApplyFailedError, "apply_failed"),
    (NotADjlibDatabaseError, "not_a_library"),
    (SchemaTooNewError, "library_too_new"),
    (NotFoundError, "not_found"),
    (RuleError, "invalid_rule"),
    (AdapterError, "adapter_error"),
    (EnrichError, "enrich_error"),
    (PlanError, "plan_error"),
    (SnapshotError, "snapshot_error"),
    (StoreError, "store_error"),
    (OSError, "os_error"),
)

_json_errors: contextvars.ContextVar[bool] = contextvars.ContextVar("json_errors", default=False)


def error_code(error: Exception) -> str:
    return next(code for kind, code in ERROR_CODES if isinstance(error, kind))


def fail(message: str, code: str = "invalid_argument", **details: JSONValue) -> NoReturn:
    """Print ``message`` on standard error, as JSON under ``--json``, and exit with code 1."""
    if _json_errors.get():
        error: dict[str, JSONValue] = {"code": code, "message": message, **details}
        typer.echo(json.dumps({"error": error}, ensure_ascii=False), err=True)
    else:
        typer.echo(f"error: {message}", err=True)
    raise typer.Exit(1)


@contextlib.contextmanager
def reported_errors(as_json: bool = False) -> Generator[None]:
    """Turn expected failures into a one-line message, JSON with ``as_json``, and exit code 1."""
    token = _json_errors.set(as_json)
    try:
        yield
    except ApplyFailedError as error:
        details: dict[str, JSONValue] = {
            "target": error.target,
            "snapshot": error.snapshot,
            "restored": error.restored,
        }
        if error.restored or as_json:
            fail(str(error), "apply_failed", **details)
        restore = f"djlib snapshot restore {error.target} {error.snapshot} --apply"
        fail(f"{error}\nrun: {restore}", "apply_failed", **details)
    except EXPECTED_ERRORS as error:
        fail(str(error), error_code(error))
    finally:
        _json_errors.reset(token)


def confirm(question: str, *, yes: bool, as_json: bool, refused: str) -> bool:
    """Whether to go on: ``--yes``, or the user's answer on an interactive terminal.

    Without a terminal and without ``--yes``, fails with ``refused`` and a hint.
    """
    if yes:
        return True
    if not stdin_is_interactive():
        fail(f"{refused}: confirmation needs an interactive terminal; pass --yes", "needs_yes")
    return typer.confirm(question, default=False, err=as_json)


def stdin_is_interactive() -> bool:
    return sys.stdin.isatty()


def stderr_is_interactive() -> bool:
    return sys.stderr.isatty()


class FolderProgress:
    """Shows, on one line of standard error, how many files a folder walk has seen."""

    def __init__(self) -> None:
        self._shown = False

    def __call__(self, folder: Path, seen: int) -> None:
        sys.stderr.write(f"\r\033[KSearching {folder}: {seen} files")
        sys.stderr.flush()
        self._shown = True

    def clear(self) -> None:
        if self._shown:
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()
            self._shown = False


def run(
    ctx: typer.Context,
    make_plan: Callable[[Engine], Plan],
    *,
    apply: bool,
    yes: bool,
    as_json: bool,
) -> None:
    """Plan with ``make_plan``, show the plan, and apply it when asked and confirmed."""
    home = home_of(ctx)
    progress = FolderProgress() if stderr_is_interactive() else None
    with reported_errors(as_json), home.engine(progress=progress) as engine:
        try:
            plan = make_plan(engine)
        finally:
            if progress is not None:
                progress.clear()
        if not as_json:
            typer.echo(render_text(plan), nl=False)
        result = None
        if apply:
            result = _apply(home, engine, plan, yes=yes, as_json=as_json)
        if as_json:
            typer.echo(json.dumps(to_json(plan, result), ensure_ascii=False, indent=2))
        else:
            _report(plan, result)


def _apply(home: Home, engine: Engine, plan: Plan, *, yes: bool, as_json: bool) -> ApplyResult:
    if plan.empty:
        return engine.apply(plan, assume_yes)
    if as_json and not (yes or stdin_is_interactive()):
        typer.echo(json.dumps(to_json(plan), ensure_ascii=False, indent=2))
    if not confirm("Apply this plan?", yes=yes, as_json=as_json, refused="not applied"):
        return ApplyResult(status="declined")
    return home.apply(engine, plan)


def _report(plan: Plan, result: ApplyResult | None) -> None:
    if result is None:
        if not plan.empty:
            typer.echo("Dry run: nothing was written. Run again with --apply to apply it.")
        return
    if result.status == "declined":
        typer.echo("Not applied.")
    elif result.status == "applied":
        typer.echo(
            f"Applied. Snapshot {result.snapshot} of {plan.target} holds the previous state."
        )
        if result.files_trashed:
            files = "file" if result.files_trashed == 1 else "files"
            typer.echo(f"Moved {result.files_trashed} {files} to the system trash.")
    for warning in result.warnings:
        typer.echo(f"warning: {warning}", err=True)
