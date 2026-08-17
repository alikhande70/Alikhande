"""Application-owned filesystem locations, without importing Qt."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_directory() -> Path:
    """Return the durable per-user data directory and ensure it exists."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / "AlikhandeScanner"
    path.mkdir(parents=True, exist_ok=True)
    return path
