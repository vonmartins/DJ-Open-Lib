"""Renaming files without ever overwriting one, also when only the case of the name changes."""

import os
import secrets
from pathlib import Path


def case_only(old: Path, new: Path) -> bool:
    """Whether ``new`` is ``old`` with only the case of its name changed."""
    # Strings, not paths: Windows paths compare equal ignoring case.
    return (
        old.name != new.name
        and os.fspath(old.parent) == os.fspath(new.parent)
        and old.name.casefold() == new.name.casefold()
    )


def name_free(old: Path, new: Path) -> bool:
    """Whether ``old`` can take the name ``new`` without replacing another file.

    On file systems that ignore case, a case-only change finds ``old`` itself at ``new``.
    """
    if not os.path.lexists(new):
        return True
    return case_only(old, new) and old.samefile(new)


def move_file(old: Path, new: Path) -> None:
    """Rename ``old`` to ``new``; a case-only change goes through a temporary name."""
    if not name_free(old, new):
        raise FileExistsError(f"{new} already exists")
    if case_only(old, new):
        temporary = old.with_name(f".{old.name}.tunedex-{secrets.token_hex(4)}.tmp")
        old.rename(temporary)
        try:
            temporary.rename(new)
        except OSError:
            temporary.rename(old)
            raise
        return
    old.rename(new)
