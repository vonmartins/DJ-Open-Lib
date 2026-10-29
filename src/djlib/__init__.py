"""Free, local-first, scriptable DJ library manager.

The names below are the API that programs may rely on; other modules are internal.

    import djlib

    with djlib.open_library() as engine:
        plan = engine.plan_scan("/path/to/music")
        print(djlib.render_text(plan))
"""

from djlib.adapters.errors import AdapterError
from djlib.enrich.errors import EnrichError
from djlib.home import Home, default_home, open_library, resolve_home
from djlib.planning import (
    ApplyFailedError,
    ApplyResult,
    Confirm,
    Engine,
    Plan,
    PlanError,
    StaleTargetError,
    UnknownPlaylistError,
    assume_yes,
    render_text,
    to_json,
)
from djlib.query import (
    Status,
    TrackView,
    TreeNode,
    find_track,
    parse_where,
    playlist_tree,
    select,
    status,
    track_view,
)
from djlib.rules.errors import RuleError
from djlib.snapshots import SnapshotError
from djlib.store.errors import StoreError

__all__ = [
    "AdapterError",
    "ApplyFailedError",
    "ApplyResult",
    "Confirm",
    "Engine",
    "EnrichError",
    "Home",
    "Plan",
    "PlanError",
    "RuleError",
    "SnapshotError",
    "StaleTargetError",
    "Status",
    "StoreError",
    "TrackView",
    "TreeNode",
    "UnknownPlaylistError",
    "assume_yes",
    "default_home",
    "find_track",
    "open_library",
    "parse_where",
    "playlist_tree",
    "render_text",
    "resolve_home",
    "select",
    "status",
    "to_json",
    "track_view",
]
