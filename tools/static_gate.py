#!/usr/bin/env python3
"""Alikhande Scanner static gate.

No MetaEditor is available in CI or in the agent sandbox, so this is the only
automated correctness gate the project has. It is deliberately strict: a clean
run does not prove the code compiles, but a failing run always means something
is genuinely wrong.

Usage:
    python3 tools/static_gate.py            # full gate, exits non-zero on failure
    python3 tools/static_gate.py --warn-only  # report but always exit 0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mql5lint import checks  # noqa: E402
from mql5lint.model import SourceTree  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MQL5 = ROOT / "MQL5"
INCLUDE_ROOT = MQL5 / "Include"

ORDER_SEND_OWNER = "MQL5/Include/AlikhandeScanner/Execution/ExecutionEngine.mqh"

REQUIRED_INVARIANTS = {
    "real account hard block": "REAL_ACCOUNT_BLOCKED",
    "demo account guard": "ACCOUNT_TRADE_MODE_DEMO",
    "trade transaction reconciliation": "OnTradeTransaction",
    "probability honesty guard": "has_historical_estimate",
}

# Checks that are advisory during the rebuild rather than hard failures.
# Each entry must carry a reason; an empty rationale is not accepted in review.
SOFT_CODES: dict[str, str] = {
    "DEAD_TYPE": "reported so unreachable modules stay visible; not fatal on its own",
}


def build_tree() -> SourceTree:
    tree = SourceTree(root=ROOT, include_root=INCLUDE_ROOT)
    sources = sorted(set(MQL5.rglob("*.mq5")) | set(MQL5.rglob("*.mqh")))
    tree.load(sources)
    return tree


def run(tree: SourceTree) -> list[checks.Finding]:
    findings: list[checks.Finding] = []
    findings += checks.check_include_graph(tree)
    findings += checks.check_include_cycles(tree)
    findings += checks.check_bracket_balance(tree)
    findings += checks.check_pragma_once(tree)
    findings += checks.check_unresolved_constants(tree)
    findings += checks.check_struct_field_access(tree)
    findings += checks.check_unchecked_copy(tree)
    findings += checks.check_indicator_handle_leak(tree)
    findings += checks.check_resize_without_init(tree)
    findings += checks.check_use_before_definition(tree)
    findings += checks.check_forbidden(tree)
    findings += checks.check_order_send_boundary(tree, ORDER_SEND_OWNER)
    findings += checks.check_required_invariants(tree, REQUIRED_INVARIANTS)
    findings += checks.check_dead_types(tree, [])
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warn-only", action="store_true")
    args = parser.parse_args()

    tree = build_tree()
    findings = run(tree)

    total_lines = sum(len(sf.text.splitlines()) for sf in tree.files.values())
    print("=" * 72)
    print("ALIKHANDE STATIC GATE")
    print("=" * 72)
    print(f"  files   : {len(tree.files)}")
    print(f"  lines   : {total_lines}")
    print(f"  types   : {len(tree.types)}")
    print()

    hard = [f for f in findings if f.code not in SOFT_CODES]
    soft = [f for f in findings if f.code in SOFT_CODES]

    if soft:
        print(f"-- advisory ({len(soft)}) " + "-" * 48)
        for f in soft:
            print(f)
        print()

    if hard:
        print(f"-- FAILURES ({len(hard)}) " + "-" * 49)
        for f in hard:
            print(f)
        print()
        print(f"RESULT: FAIL ({len(hard)} blocking, {len(soft)} advisory)")
        return 0 if args.warn_only else 1

    print(f"RESULT: PASS ({len(soft)} advisory)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
