"""Read a module's source without importing it.

Some of the strongest guards in this suite are *coupling* checks: does the
window actually read every field the robot can ask for, does every notification
subject have a title, does the backtest purge after the replay rather than
before. Unit tests cannot express those — a module with no consumers passes its
own tests perfectly — so they are written against the text of the calling
module.

The obvious way to get that text is ``inspect.getsource``, which needs the
module imported. Every one of those modules lives under ``alikhande.ui`` and
imports PySide6 at module scope, so importing them is impossible in the
dependency-free CI job. Doing it anyway is what turned a green suite into four
errors there.

Moving them into ``test_ui.py`` would have worked and would have been worse:
that file is skipped when Qt is absent, so the guards would only protect the
contract on the machine that least needs protecting. Reading the file gives
identical text with no import at all, so these run in **both** jobs.

This is the same technique ``test_the_theme_module_needs_no_qt`` already uses,
which is where the idea came from.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def module_source(*parts: str) -> str:
    """Source text of ``alikhande/<parts>``, read from disk.

    ``module_source("ui", "main_window.py")`` returns the file's text.
    """
    path = ROOT.joinpath("alikhande", *parts)
    if not path.exists():  # pragma: no cover - a moved file should fail loudly
        raise AssertionError(f"no such module file: {path}")
    return path.read_text(encoding="utf-8")


def method_source(text: str, name: str) -> str:
    """The body of one ``def name(...)`` block, at whatever indentation it sits.

    Handles module-level functions and methods alike: ``_cmd_calibrate`` is a
    plain function and ``_drive_robot`` is a method, and a slicer that assumed
    one indentation silently failed to find the other.

    Crude on purpose. A real parse would need ``ast``, and ``ast`` gives back a
    tree these checks would then have to walk looking for attribute access —
    more machinery than "does this string appear inside this block" needs.

    Raises rather than returning empty when the definition is missing: a
    coupling guard that silently passes because it could not find what it was
    checking is worse than no guard, since it reports a property nobody
    verified.
    """
    lines = text.splitlines()
    opener = f"def {name}("

    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith(opener):
            continue
        indent = len(line) - len(stripped)

        body = [line]
        for following in lines[index + 1 :]:
            if not following.strip():
                body.append(following)
                continue
            # The first non-blank line at or left of the opener's indentation
            # begins something else.
            if len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        return "\n".join(body)

    raise AssertionError(
        f"definition `{name}` not found — it was renamed or removed, and the "
        "guard that depends on it is now checking nothing"
    )
