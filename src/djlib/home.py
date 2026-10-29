"""The djlib home: the directory holding the library database, the snapshots and the cache."""

import contextlib
import os
import sys
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from djlib.planning import ApplyResult, Confirm, Engine, Plan, assume_yes
from djlib.planning.relocating import Progress
from djlib.snapshots import SnapshotStore
from djlib.store import Store

DATABASE = "library.db"
SNAPSHOTS = "snapshots"
RULES = "rules.yaml"
CACHE = "cache.db"
HOME_VARIABLE = "DJLIB_HOME"


def default_home() -> Path:
    """The per-OS user data directory for djlib."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "djlib"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "djlib"
    base = os.environ.get("XDG_DATA_HOME", "")
    # The XDG spec says relative values are invalid and must be ignored.
    root = Path(base) if base and Path(base).is_absolute() else Path.home() / ".local" / "share"
    return root / "djlib"


def resolve_home(path: str | os.PathLike[str] | None = None) -> Path:
    """``path``, else ``DJLIB_HOME``, else the default home; ``~`` expanded, made absolute."""
    chosen = path if path is not None else os.environ.get(HOME_VARIABLE) or default_home()
    return Path(chosen).expanduser().absolute()


@dataclass(frozen=True, slots=True)
class Home:
    path: Path

    @property
    def database(self) -> Path:
        return self.path / DATABASE

    @property
    def snapshots(self) -> SnapshotStore:
        return SnapshotStore(self.path / SNAPSHOTS)

    @property
    def rules_file(self) -> Path:
        return self.path / RULES

    @property
    def cache_file(self) -> Path:
        return self.path / CACHE

    @property
    def exists(self) -> bool:
        """Whether the library database was created."""
        return self.database.exists()

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
        exists = create or self.exists
        with Store.open(str(self.database) if exists else ":memory:") as store:
            yield Engine(store, self.snapshots, progress=progress)

    def apply(self, engine: Engine, plan: Plan, confirm: Confirm = assume_yes) -> ApplyResult:
        """Apply ``plan``, made with ``engine`` on this home.

        A plan made on the in-memory library of a new home is applied to a library
        created in the home, so planning first and applying later works in a new home too.
        """
        if engine.store.path is not None or plan.empty:
            return engine.apply(plan, confirm)
        with self.engine(create=True) as created:
            return created.apply(plan, confirm)


def open_library(
    home: str | os.PathLike[str] | None = None,
    *,
    create: bool = False,
    progress: Progress | None = None,
) -> contextlib.AbstractContextManager[Engine]:
    """An engine on the library of ``home``, resolved as the command line does.

    Use it as ``with open_library() as engine:``. In a home without a library, the
    engine plans on an empty in-memory library and creates nothing; pass ``create`` to
    create the library, or apply with ``Home.apply``.
    """
    return Home(resolve_home(home)).engine(create=create, progress=progress)
