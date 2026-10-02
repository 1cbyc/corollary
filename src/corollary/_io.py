"""File helpers shared by snapshot writers."""

from __future__ import annotations

import os
import stat
import tempfile
import time
from pathlib import Path

_REPLACE_ATTEMPTS = 5


def write_atomically(path: str | os.PathLike[str], text: str) -> None:
    """Write ``text`` to ``path`` so that a crash mid-write never leaves a truncated file: the
    content goes to a temporary file in the same directory, which then replaces ``path``.

    A symlink is followed, so the file it points to is replaced, not the link. An existing file
    keeps its permissions; a new one is readable by its owner only, since a snapshot may hold
    sensitive data. On Windows, replacing a file another process has open can fail;
    after a few retries the content is written in place instead, as a plain write would.
    """
    target = Path(os.path.realpath(path))
    mode = _mode_for(target)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        _replace(temp, target, text)
    finally:
        Path(temp).unlink(missing_ok=True)


def _mode_for(target: Path) -> int | None:
    try:
        return stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        return None


def _replace(temp: str, target: Path, text: str) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(temp, target)
            return
        except PermissionError:
            if os.name != "nt":
                raise
            time.sleep(0.05 * (attempt + 1))  # another process (a reader, an antivirus) holds it
    target.write_text(text, encoding="utf-8")
