"""File helpers shared by snapshot writers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomically(path: str | os.PathLike[str], text: str) -> None:
    """Write ``text`` to ``path`` so that a crash mid-write never leaves a truncated file: the
    content goes to a temporary file in the same directory, which then replaces ``path``."""
    target = Path(path)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
