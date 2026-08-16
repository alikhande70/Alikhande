"""The dependency-free core, asserted rather than assumed.

``alikhande.core`` importing nothing outside the standard library is the
property the whole test strategy rests on: it is why the analysis engines, the
risk model, the execution state machine and the outcome loop can all be
exercised on a machine with no MetaTrader, no Qt and no database — which is the
single biggest difference from the MQL5 build.

Until this file existed, **nothing checked it.** The dependency-free CI job runs
the suite with PySide6 blocked, and that is weaker evidence than it looks: it
proves core does not need *Qt*. It would not have noticed `import numpy`, or
`import MetaTrader5`, or — the more likely mistake — a core module reaching
sideways into `alikhande.adapters` for something convenient.

So this walks the source with `ast` and checks two things.

**Nothing outside the standard library.** An allowlist rather than a denylist,
because the failure mode being prevented is somebody adding a dependency
without noticing, and a denylist only catches the ones already thought of.

**No import from an outer layer.** ``core`` is the innermost ring: ``adapters``,
``app`` and ``ui`` may all depend on it and it may depend on none of them. That
direction is what makes the ports/adapters split real rather than decorative,
and it is not visible to any runtime test — a core module importing an adapter
works perfectly until the day somebody tries to run core without one.

``ast`` rather than a regex, because a regex over source text matches imports
inside docstrings and misses ``import x as y``.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "alikhande" / "core"

#: Standard-library modules ``core`` is permitted to import.
#:
#: Deliberately short. Every addition here is a decision that the pure core now
#: depends on one more thing, and it should be made on purpose — which is what
#: a test failure forces.
ALLOWED_STDLIB = {
    "__future__",
    "collections",
    "dataclasses",
    "datetime",
    "enum",
    "math",
    "pathlib",
    "time",
    "typing",
}

#: Layers ``core`` must never import from. The ring below it does not exist.
FORBIDDEN_LAYERS = ("adapters", "app", "ui")


def core_modules() -> list[Path]:
    return sorted(p for p in CORE.glob("*.py") if p.name != "__init__.py")


def imports_of(path: Path) -> list[tuple[str, int]]:
    """``(module, lineno)`` for every import in one file.

    A relative import comes back with a leading dot count so the layer check
    can tell ``from .enums import`` (fine, same ring) from ``from ..adapters``
    (not fine).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level + (node.module or ""), node.lineno))
    return found


class TestCoreIsDependencyFree(unittest.TestCase):
    def test_there_are_core_modules_to_check(self):
        """A guard on the guard. If the glob stopped matching, every test below
        would pass by iterating over nothing."""
        self.assertGreater(len(core_modules()), 15)

    def test_core_imports_only_the_standard_library(self):
        offenders: list[str] = []
        for path in core_modules():
            for module, line in imports_of(path):
                if module.startswith("."):
                    continue  # a sibling in the same ring; the next test judges it
                root = module.split(".")[0]
                if root not in ALLOWED_STDLIB:
                    offenders.append(f"{path.name}:{line} imports {module!r}")
        self.assertEqual(
            offenders,
            [],
            "core must import nothing outside the standard library — that is what "
            "lets the whole pipeline be tested without MetaTrader, Qt or a database:\n"
            + "\n".join(offenders),
        )

    def test_core_never_imports_an_outer_layer(self):
        """``core`` is the innermost ring. adapters, app and ui depend on it;
        it depends on none of them.

        Invisible to any runtime test — a core module importing an adapter
        works perfectly until somebody tries to run core without one.
        """
        offenders: list[str] = []
        for path in core_modules():
            for module, line in imports_of(path):
                for layer in FORBIDDEN_LAYERS:
                    if module.lstrip(".").startswith(layer) or f".{layer}" in module:
                        offenders.append(f"{path.name}:{line} imports {module!r}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_core_never_imports_sqlite(self):
        """Persistence is an adapter concern. The repositories implement a
        protocol core defines; core knowing what a cursor is would invert
        that."""
        for path in core_modules():
            for module, line in imports_of(path):
                self.assertNotIn(
                    "sqlite", module, f"{path.name}:{line} imports {module!r}"
                )

    def test_core_never_imports_metatrader(self):
        """The gateway protocol is the whole boundary. There is exactly one
        module in this package permitted to import MetaTrader5 and it is an
        adapter."""
        for path in core_modules():
            for module, _line in imports_of(path):
                self.assertNotIn("MetaTrader5", module, path.name)

    def test_only_the_mt5_adapter_imports_metatrader(self):
        """Stated as a package-wide property, not just a core one."""
        importers = []
        for path in (ROOT / "alikhande").rglob("*.py"):
            for module, _line in imports_of(path):
                if "MetaTrader5" in module:
                    importers.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            sorted(set(importers)), ["alikhande/adapters/mt5/gateway.py"]
        )


class TestTheAllowlistIsHonest(unittest.TestCase):
    """The allowlist is only meaningful if it is actually restrictive."""

    def test_the_allowlist_would_reject_a_third_party_import(self):
        offenders = [m for m in ("numpy", "requests", "PySide6") if m in ALLOWED_STDLIB]
        self.assertEqual(offenders, [])

    def test_every_allowlisted_module_is_actually_importable(self):
        """A typo in the allowlist silently widens it — an entry that matches
        nothing real still lets a module through if somebody imports that
        misspelling."""
        import importlib

        for name in sorted(ALLOWED_STDLIB - {"__future__"}):
            importlib.import_module(name)


if __name__ == "__main__":
    unittest.main()
