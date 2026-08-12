"""Render every view to PNG so the interface can be looked at, not imagined.

Run it after any change to the UI:

    QT_QPA_PLATFORM=offscreen python3 tools/render_ui.py --out /tmp/shots

Offscreen rendering is the whole point. A design decision that survives being
described in a commit message and dies on contact with a screenshot is one
nobody checked, and the failures this catches — a clipped axis, a chip that
became invisible in light mode, a column with no room for its number — are
exactly the ones no unit test will ever see.

It drives the real window against the offline gateway, so what is captured is
the application, not a mock of it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def render(out: Path, language: str, theme: str, settle_passes: int = 12) -> list[Path]:
    from PySide6.QtCore import Qt

    from alikhande.i18n import is_rtl, set_language
    from alikhande.ui import main_window as mw
    from alikhande.ui.main_window import NAV
    from alikhande.ui.theme import set_theme

    application, window = mw.build_application(offline=True)

    # ``build_application`` restores whatever the stored preferences say, so the
    # language and theme are forced afterwards rather than before. The
    # retranslate rebuilds every view, which is exactly how the application
    # itself applies both switches — so what gets captured is the real path,
    # not a special rendering mode.
    set_language(language)
    set_theme(theme)
    application.setStyleSheet(mw.stylesheet())
    application.setLayoutDirection(
        Qt.LayoutDirection.RightToLeft if is_rtl() else Qt.LayoutDirection.LeftToRight
    )
    window._retranslate()
    window.resize(1560, 960)
    window.show()

    # Let the scan worker produce real snapshots. Rendering before the first
    # pass captures empty states, which is a screenshot of the loading screen
    # rather than of the application.
    deadline = time.time() + 25.0
    while time.time() < deadline:
        application.processEvents()
        if getattr(window, "_passes_seen", 0) >= settle_passes:
            break
        time.sleep(0.05)
    for _ in range(60):
        application.processEvents()

    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, (_icon, key, _tip) in enumerate(NAV):
        window._stack.setCurrentIndex(index)
        for _ in range(12):
            application.processEvents()
        name = key.split(".", 1)[1]
        path = out / f"{theme}_{language}_{index}_{name}.png"
        window.grab().save(str(path))
        written.append(path)

    window._worker.stop()
    window._thread.quit()
    window._thread.wait(2000)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/tmp/alikhande-shots")
    parser.add_argument("--languages", default="en,fa")
    parser.add_argument("--themes", default="dark,light")
    args = parser.parse_args()

    out = Path(args.out)
    for theme in args.themes.split(","):
        for language in args.languages.split(","):
            for path in render(out, language.strip(), theme.strip()):
                print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
