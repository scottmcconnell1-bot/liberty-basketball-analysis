"""Small file helpers shared by the unattended ops scripts."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write *text* to *path* so readers see either the old or the new file, never half.

    Writes a temp file in the same folder, fsyncs it, then os.replace()s it over
    the target. On Windows os.replace can briefly fail while another process has
    the target open, so it is retried for a few seconds.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.25)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
