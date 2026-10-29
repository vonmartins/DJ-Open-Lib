"""The flow every writing command shares: plan, show, confirm, apply, report."""

import contextlib
import json
import sys
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import typer

from djlib.adapters.errors import AdapterError
from djlib.cli._home import DATABASE, SNAPSHOTS
from djlib.enrich import EnrichError
from djlib.planning import (
    ApplyFailedError,
    ApplyResult,
    Engine,
    Plan,
    PlanError,
    assume_yes,
    render_text,
    to_json,
)
from djlib.planning.relocating import Progress
from djlib.rules import RuleError
from djlib.snapshots import SnapshotError, SnapshotStore
from djlib.store import Store, StoreError

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


@dataclass(frozen=True, slots=True)
class Home:
    path: Path

    @property
    def database(self) -> Path:
        return self.path / DATABASE

    @property
    def snapshots(self) -> SnapshotStore:
        return SnapshotStore(self.path / SNAPSHOTS)

    @contextlib.contextmanager
    def engine(
        self, *, create: bool = False, progress: Progress | None = None
    ) -> Generator[Engine]:
        """An engine on the library.

        Without ``create``, a home that has no library yet gets an in-memory one, so
        planning there creates nothing.
        """
        if create:
            self.path.mkdir(parents=True, exist_ok=True)
        exists = create or self.database.exists()
        with Store.open(str(self.database) if exists else ":memory:") as store:
            yield Engine(store, self.snapshots, progress=progress)


def home_of(ctx: typer.Context) -> Home:
    home = ctx.find_root().obj
    assert isinstance(home, Home)  # noqa: S101 - set by the root callback
    return home


def fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(1)


@contextlib.contextmanager
def reported_errors() -> Generator[None]:
    """Turn expected failures into a one-line message and exit code 1."""
    try:
        yield
    except ApplyFailedError as error:
        hint = (
            ""
            if error.restored
            else (f"\nrun: djlib snapshot restore {error.target} {error.snapshot}")
        )
        fail(f"{error}{hint}")
    except EXPECTED_ERRORS as error:
        fail(str(error))


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
    with reported_errors(), home.engine(progress=progress) as engine:
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
    if not (yes or stdin_is_interactive()):
        if as_json:
            typer.echo(json.dumps(to_json(plan), ensure_ascii=False, indent=2))
        fail("not applied: confirmation needs an interactive terminal; pass --yes")
    if not (yes or _ask(as_json)):
        return ApplyResult(status="declined")
    if engine.store.path is not None:
        return engine.apply(plan, assume_yes)
    # Planned against the in-memory library of a new home: create it and apply there.
    with home.engine(create=True) as created:
        return created.apply(plan, assume_yes)


def _ask(as_json: bool) -> bool:
    return typer.confirm("Apply this plan?", default=False, err=as_json)


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
