"""The flow every writing command shares: plan, show, confirm, apply, report."""

import contextlib
import contextvars
import json
import sys
from collections.abc import Callable, Generator
from typing import NoReturn

import typer

from tunedex.adapters.errors import AdapterError
from tunedex.cli import _console
from tunedex.cli._progress import FolderProgress
from tunedex.enrich import EnrichError
from tunedex.home import Home
from tunedex.model.unmapped import JSONValue
from tunedex.planning import (
    ApplyFailedError,
    ApplyResult,
    Engine,
    Plan,
    PlanError,
    StaleTargetError,
    UnknownPlaylistError,
    assume_yes,
    to_json,
)
from tunedex.planning.render import plan_lines
from tunedex.rules import RuleError
from tunedex.snapshots import SnapshotError
from tunedex.store import NotATunedexDatabaseError, NotFoundError, SchemaTooNewError, StoreError

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
    (NotATunedexDatabaseError, "not_a_library"),
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
        _console.echo_spans([("error:", "error"), (f" {message}", None)], err=True)
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
        restore = f"tunedex snapshot restore {error.target} {error.snapshot} --apply"
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
            _console.echo_rows(plan_lines(plan))
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
            _console.echo(
                "Dry run: nothing was written. Run again with --apply to apply it.", "notice"
            )
        return
    if result.status == "declined":
        _console.echo("Not applied.", "notice")
    elif result.status == "applied":
        _console.echo(
            f"Applied. Snapshot {result.snapshot} of {plan.target} holds the previous state.",
            "added",
        )
        if result.files_trashed:
            files = "file" if result.files_trashed == 1 else "files"
            _console.echo(f"Moved {result.files_trashed} {files} to the system trash.", "trash")
    for warning in result.warnings:
        _console.echo_spans([("warning:", "warning"), (f" {warning}", None)], err=True)
