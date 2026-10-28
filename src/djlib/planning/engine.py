"""The only write path: plan, confirm, check the target is unchanged, snapshot, write, restore.

Planning never writes. Applying takes a confirmation decision from the caller and
does nothing without it.
"""

import datetime
import hashlib
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from djlib.adapters.contract import Adapter, ReadOptions, WriteOptions, WritePlan
from djlib.adapters.losses import display_name
from djlib.adapters.pathmap import PathMapping
from djlib.model.library import Library
from djlib.planning.diff import diff_export, diff_scan
from djlib.planning.errors import ApplyFailedError, PlanError, StaleTargetError
from djlib.planning.exporting import export_bases, merge_export, target_paths
from djlib.planning.importing import plan_import
from djlib.planning.model import (
    LIBRARY_TARGET,
    ApplyResult,
    ExportAction,
    FieldConflict,
    LibraryAction,
    Plan,
)
from djlib.planning.selection import covered, fingerprints, modified, resolve_paths, target_name
from djlib.planning.writer import DirectoryTracker, WriteFile, write_atomically
from djlib.snapshots import SnapshotStore
from djlib.sources.folder_scan import scan_folder
from djlib.store import Store, StoreError

Confirm = Callable[[Plan], bool]


def assume_yes(plan: Plan) -> bool:
    """A confirmation that accepts every plan, for scripted use."""
    return True


class Engine:
    """Plans and applies changes to the library in ``store`` and to export targets."""

    def __init__(
        self,
        store: Store,
        snapshots: SnapshotStore,
        *,
        clock: Callable[[], datetime.datetime] | None = None,
        _write_file: WriteFile = write_atomically,
    ) -> None:
        self.store = store
        self.snapshots = snapshots
        self._clock = clock or (lambda: datetime.datetime.now(datetime.UTC))
        self._write_file = _write_file

    # Planning

    def plan_scan(self, root: str | os.PathLike[str]) -> Plan:
        """Plan bringing the library in line with the music folder ``root``."""
        revision = self.store.revision()
        scan = scan_folder(self.store, root, clock=self._clock)
        tracks, refreshed = diff_scan(self.store, scan)
        conflicts: list[FieldConflict] = []
        for conflict in scan.conflicts:
            track = self.store.get_track(conflict.track_id)
            conflicts.append(
                FieldConflict(
                    track_id=track.id,
                    path=track.path,
                    label=display_name(track),
                    field=conflict.field,
                    library_value=conflict.library_value,
                    file_value=conflict.file_value,
                )
            )
        return Plan(
            target=LIBRARY_TARGET,
            title=f"scan {scan.root}",
            action=LibraryAction(operations=scan.operations, base_revision=revision),
            tracks=tracks,
            refreshed=refreshed,
            conflicts=tuple(conflicts),
            warnings=scan.warnings,
        )

    def plan_import(
        self,
        adapter: Adapter,
        location: str | os.PathLike[str],
        *,
        path_mapping: PathMapping | None = None,
    ) -> Plan:
        """Plan importing what ``adapter`` reads at ``location`` into the library."""
        revision = self.store.revision()
        location = Path(location).absolute()
        imported = plan_import(
            self.store, adapter, location, path_mapping=path_mapping, now=self._clock()
        )
        return Plan(
            target=LIBRARY_TARGET,
            title=f"import {adapter.name} from {location}",
            action=LibraryAction(operations=imported.operations, base_revision=revision),
            tracks=imported.tracks,
            nodes=imported.nodes,
            rebased=imported.rebased,
            conflicts=imported.conflicts,
            warnings=imported.warnings,
        )

    def plan_export(
        self,
        adapter: Adapter,
        location: str | os.PathLike[str],
        *,
        playlists: Sequence[str] | None = None,
        modified_only: bool = False,
        path_mapping: PathMapping | None = None,
    ) -> Plan:
        """Plan writing the library's playlists to ``location``.

        By default every playlist is written. ``playlists`` selects nodes by path, and
        ``modified_only`` selects those changed since the last export to this target.
        """
        if playlists is not None and modified_only:
            raise PlanError("choose either selected playlists or modified ones, not both")
        location = Path(location).absolute()
        path_mapping = path_mapping or PathMapping()
        library = self.store.load_library()
        target = target_name(adapter.name, location)
        capabilities = adapter.capabilities

        selection = None
        if playlists is not None:
            selection = resolve_paths(library, playlists)
        elif modified_only:
            selection = modified(library, capabilities, self.store.sync_state(target))

        current, read_warnings = self._read_target(adapter, location, path_mapping)
        bases = self.store.source_values(target) if capabilities.collection else {}
        # Only targets holding a collection have track data of their own to respect.
        merge = merge_export(
            library, current if capabilities.collection else Library(), bases, capabilities
        )
        if selection is not None and not selection:
            write_plan = WritePlan(adapter=adapter.name, location=location)
        else:
            source = self.store.source(target)
            options = WriteOptions(
                path_mapping=path_mapping,
                selection=selection,
                source_root=None if source is None else source.root_node_id,
            )
            write_plan = adapter.plan_write(merge.library, location, options)
        view = write_plan.view
        if view is not None:
            # The view holds only what is written, already in the target's shape.
            nodes, tracks, untouched = diff_export(current, view, None, capabilities)
        else:
            nodes, tracks, untouched = diff_export(current, merge.library, selection, capabilities)
        written = covered(library, selection)
        return Plan(
            target=target,
            title=f"export {adapter.name} to {location}",
            action=ExportAction(
                adapter=adapter,
                write_plan=write_plan,
                fingerprints=fingerprints(library, capabilities, written),
                target_paths={} if view is None else target_paths(library, view),
                source_values=(
                    export_bases(library, view, bases, merge, capabilities)
                    if view is not None and capabilities.collection
                    else {}
                ),
            ),
            tracks=tracks,
            nodes=nodes,
            untouched_nodes=untouched,
            losses=write_plan.losses,
            warnings=(*write_plan.warnings, *read_warnings),
            conflicts=merge.conflicts,
        )

    def _read_target(
        self, adapter: Adapter, location: Path, path_mapping: PathMapping
    ) -> tuple[Library, tuple[str, ...]]:
        if not adapter.detect(location).matches:
            return Library(), ()
        result = adapter.read(location, ReadOptions(path_mapping=path_mapping))
        return result.library, tuple(f"reading the target: {w}" for w in result.warnings)

    # Applying

    def apply(self, plan: Plan, confirm: Confirm) -> ApplyResult:
        """Apply ``plan`` if ``confirm`` accepts it. Empty or declined plans write nothing."""
        if plan.empty:
            return ApplyResult(status="nothing")
        if not confirm(plan):
            return ApplyResult(status="declined")
        if isinstance(plan.action, LibraryAction):
            return self._apply_scan(plan, plan.action)
        return self._apply_export(plan, plan.action)

    def _apply_scan(self, plan: Plan, action: LibraryAction) -> ApplyResult:
        if self.store.revision() != action.base_revision:
            raise StaleTargetError("the library changed since the plan was made; plan again")
        database = self.store.path
        if database is None:
            raise PlanError("an in-memory library cannot be applied")
        snapshot = self.snapshots.create(plan.target, [database], reason=plan.title)
        try:
            self.store.apply_operations(action.operations, expected_revision=action.base_revision)
        except Exception as error:
            # The transaction was rolled back: the library is as it was.
            raise ApplyFailedError(plan.target, snapshot.id, restored=True, cause=error) from error
        return ApplyResult(
            status="applied", snapshot=snapshot.id, operations_applied=len(action.operations)
        )

    def _apply_export(self, plan: Plan, action: ExportAction) -> ApplyResult:
        changes = action.write_plan.changes
        for change in changes:
            _check_unchanged(change.path, change.base_sha256)
        if action.write_plan.check is not None:
            action.write_plan.check()
        # Byte copies: the snapshot must hold exactly the content the plan was based on.
        snapshot = self.snapshots.create(
            plan.target, [c.path for c in changes], reason=plan.title, exact=True
        )
        # Close the window between the check and the snapshot: the copies must match too.
        for change, record in zip(changes, snapshot.files, strict=True):
            if record.sha256 != change.base_sha256:
                raise StaleTargetError(f"{change.path} changed since the plan was made")

        directories = DirectoryTracker()
        try:
            for change in changes:
                directories.ensure(change.path.parent)
                self._write_file(change.path, change.content)
        except BaseException as error:
            restored = self._restore(snapshot.id, plan.target, directories)
            if not isinstance(error, Exception):
                raise
            raise ApplyFailedError(
                plan.target, snapshot.id, restored=restored, cause=error
            ) from error

        warnings: tuple[str, ...] = ()
        try:
            self.store.record_sync(
                plan.target,
                action.fingerprints,
                self._clock(),
                target_paths=action.target_paths,
                source_values=action.source_values,
            )
        except StoreError as error:
            warnings = (f"the files were written but the sync state was not recorded ({error})",)
        return ApplyResult(
            status="applied", snapshot=snapshot.id, files_written=len(changes), warnings=warnings
        )

    def _restore(self, snapshot_id: str, target: str, directories: DirectoryTracker) -> bool:
        try:
            self.snapshots.restore(self.snapshots.get(target, snapshot_id))
        except Exception:
            return False
        directories.remove_empty()
        return True


def _check_unchanged(path: Path, base_sha256: str | None) -> None:
    if base_sha256 is None:
        if path.exists():
            raise StaleTargetError(f"{path} was created since the plan was made")
        return
    try:
        with path.open("rb") as file:
            current = hashlib.file_digest(file, "sha256").hexdigest()
    except FileNotFoundError:
        raise StaleTargetError(f"{path} was deleted since the plan was made") from None
    if current != base_sha256:
        raise StaleTargetError(f"{path} changed since the plan was made")
