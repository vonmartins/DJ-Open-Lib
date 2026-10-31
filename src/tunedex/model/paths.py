"""Lexical path normalization, independent of the host OS and filesystem."""

import posixpath
import re
import unicodedata

from tunedex.model.errors import ValidationError

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def normalize_path(path: str, *, entity: str = "Track", field: str = "path") -> str:
    """Return the normalized form of an absolute path.

    The result uses ``/`` as separator, an upper-case drive letter for Windows
    paths, ``//server/share`` for UNC paths, Unicode NFC and no trailing
    separator. ``.`` and ``..`` are collapsed lexically; the filesystem is never
    touched. Relative paths are rejected.
    """
    if not path:
        raise ValidationError(entity, field, "must not be empty")
    if "\0" in path:
        raise ValidationError(entity, field, "must not contain NUL characters")

    if _WINDOWS_DRIVE.match(path):
        drive, rest = path[0].upper() + ":", path[2:].replace("\\", "/")
        normalized = drive + posixpath.normpath(rest)
    elif path.startswith("\\\\"):
        normalized = posixpath.normpath(path.replace("\\", "/"))
    elif path.startswith("/"):
        normalized = posixpath.normpath(path)
    else:
        raise ValidationError(entity, field, f"must be absolute: {path!r}")

    return unicodedata.normalize("NFC", normalized)
