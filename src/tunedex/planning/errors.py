"""Errors raised while planning or applying changes."""

from collections.abc import Sequence


class PlanError(Exception):
    """Base class for planning and applying errors."""


class StaleTargetError(PlanError):
    """The target changed after the plan was computed; nothing was written."""


class UnknownPlaylistError(PlanError):
    """No playlist or folder is at the given path; ``suggestions`` holds close names."""

    def __init__(self, path: str, suggestions: Sequence[str] = ()) -> None:
        self.path = path
        self.suggestions = tuple(suggestions)
        hint = f"; did you mean {', '.join(map(repr, suggestions))}?" if suggestions else ""
        super().__init__(f"no playlist or folder at {path!r}{hint}")


class ApplyFailedError(PlanError):
    """Applying failed after writing started.

    ``restored`` says whether the target was put back as it was; when it was not,
    ``snapshot`` names the snapshot to restore by hand.
    """

    def __init__(self, target: str, snapshot: str, *, restored: bool, cause: BaseException) -> None:
        self.target = target
        self.snapshot = snapshot
        self.restored = restored
        if restored:
            outcome = "the target was restored to its previous state"
        else:
            outcome = f"restoring also failed; restore by hand with snapshot {snapshot} of {target}"
        super().__init__(f"applying failed ({cause}); {outcome}")
