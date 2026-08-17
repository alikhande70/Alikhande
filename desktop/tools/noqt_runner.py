#!/usr/bin/env python3
"""Run the test suite as if PySide6 were not installed.

This is not a convenience — it is the check that keeps ``alikhande.core``
dependency-free. CI has a job that installs nothing, and this reproduces it on
a machine where Qt happens to be present, so the property can be verified
without uninstalling anything.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class BlockPySide6:
    """A meta-path finder that makes PySide6 unimportable."""

    def find_spec(self, name, path=None, target=None):
        if name == "PySide6" or name.startswith("PySide6."):
            raise ImportError(f"No module named {name!r}")
        return None


def main() -> int:
    sys.meta_path.insert(0, BlockPySide6())
    for module in [m for m in list(sys.modules) if m.startswith("PySide6")]:
        del sys.modules[module]

    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), top_level_dir=str(ROOT)
    )
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    print(
        f"no-Qt run: ran={result.testsRun} errors={len(result.errors)} "
        f"failures={len(result.failures)} skipped={len(result.skipped)}"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
