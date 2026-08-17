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

import ast
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
    """The source of one ``def name(...)`` block, found with ``ast``.

    A first version scanned indentation: find ``def name(``, then take every
    following line indented further than it. That is wrong for a multi-line
    signature, because the closing ``) -> None:`` sits at the *same*
    indentation as the ``def`` — so the slice stopped at the end of the
    parameter list and every guard using it silently checked the signature
    instead of the body. Two of them passed for the wrong reason and then
    failed the moment a signature grew.

    ``ast`` gives exact line ranges and no guessing. Matches a function at any
    nesting depth, so it finds both a module-level ``_cmd_calibrate`` and a
    method like ``Backtester.run``.

    Raises rather than returning empty when the definition is missing: a
    coupling guard that silently passes because it could not find what it was
    checking is worse than no guard, since it reports a property nobody
    verified.
    """
    tree = ast.parse(text)
    lines = text.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != name:
            continue
        end = getattr(node, "end_lineno", None) or node.lineno
        # `lineno` is 1-based and points at the `def`; decorators sit above it
        # and are not part of what these guards inspect.
        return "\n".join(lines[node.lineno - 1 : end])

    raise AssertionError(
        f"definition `{name}` not found — it was renamed or removed, and the "
        "guard that depends on it is now checking nothing"
    )
