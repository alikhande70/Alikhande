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

**Nothing outside the standard library.** Judged against
``sys.stdlib_module_names`` rather than a hand-written allowlist. A list has to
be extended every time somebody imports a normal module — this one failed first
on ``csv`` and ``uuid`` — and a list people are used to extending is a list a
third-party import eventually gets waved through.

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
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "alikhande" / "core"

#: ``core`` may import from the standard library and nothing else.
#:
#: Asked of the interpreter rather than hand-listed. A hand-written allowlist
#: is a proxy for "is this stdlib", and it drifts: the first version of this
#: test failed on ``csv`` and ``uuid``, both of which are stdlib and both of
#: which core may legitimately use — a list that has to be extended every time
#: somebody imports a normal module trains people to extend it without thinking,
#: which is exactly how a third-party import would eventually get waved through.
#:
#: ``sys.stdlib_module_names`` is the real answer to the real question, and it
#: still rejects numpy, requests, PySide6 and MetaTrader5.
STDLIB = set(sys.stdlib_module_names) | {"__future__"}

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
                if root not in STDLIB:
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


class TestTheStdlibCheckIsHonest(unittest.TestCase):
    """The check is only meaningful if it actually rejects things."""

    def test_it_rejects_the_dependencies_this_project_actually_has(self):
        """The three that would matter: the UI toolkit, the broker package, and
        the numeric library the broker package drags in."""
        for third_party in ("PySide6", "MetaTrader5", "numpy"):
            self.assertNotIn(third_party, STDLIB)

    def test_it_accepts_what_core_legitimately_uses(self):
        for stdlib in ("dataclasses", "enum", "typing", "csv", "uuid", "math"):
            self.assertIn(stdlib, STDLIB)


if __name__ == "__main__":
    unittest.main()
