"""Atomic file replacement helpers (stdlib only, no Qt, no domain imports).

Writing a file with ``open(path, "w")`` truncates the destination *before* the
new content is produced. If the process dies mid-write — power loss, a full
disk, a crash — the user is left with a truncated file, and for
``settings.json`` that means silently losing every stored API key.

The fix is the standard write-temp / fsync / rename dance. The temporary file
must live in the *same directory* as the destination so that ``os.replace()``
is a same-filesystem rename, which POSIX (and ``MoveFileEx`` on Windows)
performs atomically.
"""

import os
import tempfile
from typing import Optional

#: Prefix/suffix for the scratch file. The leading dot keeps it out of casual
#: listings on POSIX and makes its temporary nature obvious.
TEMP_PREFIX = ".srt4u-tmp-"
TEMP_SUFFIX = ".tmp"


def atomic_write_text(
    path: str,
    content: str,
    *,
    encoding: str = "utf-8",
    permissions: Optional[int] = None,
    fsync: bool = True,
) -> None:
    """Write ``content`` to ``path`` atomically.

    The destination is only ever replaced by a fully written, fsynced file. If
    anything fails, the previous contents survive untouched and the temporary
    file is removed.

    ``permissions`` is applied to the temporary file *before* the rename, so
    the secret never exists on disk under a wider mode than intended.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    handle = None
    tmp_path: Optional[str] = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=TEMP_PREFIX, suffix=TEMP_SUFFIX
        )
        handle = os.fdopen(fd, "w", encoding=encoding, newline="")
        handle.write(content)
        handle.flush()
        if fsync:
            os.fsync(handle.fileno())
        handle.close()
        handle = None
        if permissions is not None:
            os.chmod(tmp_path, permissions)
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if tmp_path is not None and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _fsync_directory(directory: str) -> None:
    """Best-effort durability for the rename itself (no-op where unsupported)."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
