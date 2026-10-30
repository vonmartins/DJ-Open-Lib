"""Progress of slow work on standard error, erased when the work ends.

Commands create these only when standard error is a terminal; the core sees plain callables.
"""

from pathlib import Path

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from djlib.cli import _console


class _Shown:
    """A progress display started on the first report and stopped by :meth:`clear`."""

    def __init__(self, *columns: ProgressColumn | str) -> None:
        self._columns = columns
        self._progress: Progress | None = None
        self._task = TaskID(0)

    def _show(self, description: str, *, completed: int, total: int | None) -> None:
        if self._progress is None:
            self._progress = Progress(
                *self._columns, console=_console.console(err=True, terminal=True), transient=True
            )
            self._progress.start()
            self._task = self._progress.add_task(description, total=total)
        self._progress.update(self._task, description=description, completed=completed, total=total)

    def clear(self) -> None:
        if self._progress is not None:
            self._progress.stop()
            self._progress = None


class FolderProgress(_Shown):
    """A spinner with how many files a folder walk has seen, then the folder.

    The count comes first: a terminal narrower than the line cuts its end.
    """

    def __init__(self) -> None:
        super().__init__(
            SpinnerColumn(), TextColumn("Searching: {task.completed} files  {task.description}")
        )

    def __call__(self, folder: Path, seen: int) -> None:
        self._show(str(folder), completed=seen, total=None)


class StepProgress(_Shown):
    """A bar with how many tracks were enriched out of how many."""

    def __init__(self) -> None:
        super().__init__(
            TextColumn("Enriching"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("tracks"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
        )

    def __call__(self, done: int, total: int) -> None:
        self._show("Enriching", completed=done, total=total)
