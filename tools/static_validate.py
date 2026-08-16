#!/usr/bin/env python3
"""Repository-wide static acceptance gate.

This branch contains both the MQL5 scanner and the standalone desktop path.
The older validator restored by the v1.3 governance files named modules from a
different tree and crashed before checking anything. This gate delegates the
MQL5 graph/lint work to the branch's maintained static gate, then asserts the
desktop invariants that must be mechanically true before Windows runtime work.
"""

from __future__ import annotations

import ast
import compileall
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "desktop" / "alikhande"
errors: list[str] = []


def require(path: str) -> str:
    target = ROOT / path
    if not target.exists():
        errors.append(f"MISSING_REQUIRED_FILE {path}")
        return ""
    return target.read_text(encoding="utf-8", errors="replace")


# Governance has to travel with the code; an acceptance contract that exists
# only on another branch cannot govern this one.
for governed in (
    ".ai/PROJECT_DIRECTOR.md",
    ".ai/PROJECT_DIRECTOR_V1.3.md",
    "docs/PROJECT_CONSTITUTION.md",
    "docs/CODEX_ACCEPTANCE_CONTRACT.md",
):
    require(governed)


# The maintained MQL5 gate owns include reachability, OrderSend uniqueness,
# syntax structure and its adversarial self-tests.
mql_gate = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "static_gate.py")],
    cwd=ROOT,
    text=True,
    capture_output=True,
)
if mql_gate.returncode:
    errors.append("MQL5_STATIC_GATE_FAILED\n" + mql_gate.stdout + mql_gate.stderr)


if not compileall.compile_dir(str(PACKAGE), quiet=1):
    errors.append("DESKTOP_PYTHON_COMPILE_FAILED")


# Exactly one application call may cross the send boundary. Protocol
# declarations and adapter implementations are not calls by a consumer.
send_call = re.compile(r"\bsend_order\s*\(")
send_offenders: list[str] = []
for path in PACKAGE.rglob("*.py"):
    relative = path.relative_to(PACKAGE).as_posix()
    if relative in ("core/execution.py", "core/ports.py") or relative.startswith("adapters/"):
        continue
    if send_call.search(path.read_text(encoding="utf-8")):
        send_offenders.append(relative)
if send_offenders:
    errors.append("DESKTOP_SEND_BOUNDARY " + ",".join(send_offenders))


# The GUI owns no live object. ScanWorker is the only UI module allowed to
# import the engine, MT5 adapter or SQLite repository. BacktestView imports only
# the offline gateway and publishes through a separate BacktestWorker.
ui_root = PACKAGE / "ui"
for path in ui_root.rglob("*.py"):
    relative = path.relative_to(ui_root).as_posix()
    if relative == "worker.py":
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(
                module.endswith(suffix)
                for suffix in ("app.engine", "adapters.mt5", "adapters.sqlite")
            ):
                errors.append(f"UI_LIVE_IMPORT {relative}: {module}")
        if isinstance(node, ast.Attribute) and node.attr in ("_engine", "_repo"):
            errors.append(f"UI_LIVE_REFERENCE {relative}: {node.attr}")

window = require("desktop/alikhande/ui/main_window.py")
worker = require("desktop/alikhande/ui/worker.py")
for forbidden in ("probe_terminal", "MT5Gateway", "OfflineGateway"):
    if forbidden in window:
        errors.append(f"UI_COMPOSITION_TOUCHES_GATEWAY {forbidden}")
for forbidden in ("WorkerBootstrap | ScanEngine", "isinstance(bootstrap, ScanEngine)"):
    if forbidden in worker:
        errors.append(f"WORKER_ACCEPTS_PREBUILT_LIVE_STATE {forbidden}")
maintenance = require("desktop/alikhande/app/maintenance.py")
if "import MetaTrader5" in maintenance:
    errors.append("UI_DIAGNOSTICS_IMPORTS_MT5")


execution = require("desktop/alikhande/core/execution.py")
for needle in (
    "correlation_key",
    "self._comment_matches",
    "deal.position_id in position_ids",
    "position contains an entry without a direct execution link",
    "now - self._current.created_at <= grace",
    "ORDER_SEND_UNCERTAIN",
    "UNRELATED_DEAL_IGNORED",
    "exact broker sources disagree on position identity",
    "FOREIGN_NETTING_ENTRY_REQUIRES_MANUAL_REVIEW",
    'or "UNKNOWN" for deal in exits',
):
    if needle not in execution:
        errors.append(f"EXACT_RECONCILIATION_GUARD_MISSING {needle}")
if "magic + symbol" in execution.lower():
    errors.append("SYMBOL_GUESS_REINTRODUCED")

engine = require("desktop/alikhande/app/engine.py")
for needle in (
    "DealLedger(self._repo.record_deal_once)",
    "load_execution_awaiting_outcome",
    "evidence_quality=\"BROKER_DEALS\" if truth.deals",
    "evidence_quality=\"PREFLIGHT_ONLY\"",
    "save_outcome_with_state",
    "return copy.deepcopy(snapshot)",
    "positions_known",
    "_refresh_broker_state",
    "BROKER_POSITIONS_UNAVAILABLE",
    "evidence_signal_id(signal, signal.broker_spec_hash)",
    "refresh_gateway_state",
):
    if needle not in engine:
        errors.append(f"DEMO_EVIDENCE_WIRING_MISSING {needle}")

repositories = require("desktop/alikhande/adapters/sqlite/repositories.py")
for needle in (
    "INSERT OR IGNORE INTO outcomes",
    "replace_runs_of_kind_from",
    "BEGIN IMMEDIATE",
    "finished_at IS NULL",
    "valid_for_statistics = 1",
    "SignalIdentityCollision",
    'existing["parameter_hash"]',
    'existing["broker_spec_hash"]',
):
    if needle not in repositories:
        errors.append(f"EVIDENCE_INTEGRITY_GUARD_MISSING {needle}")

database = require("desktop/alikhande/adapters/sqlite/database.py")
if "execution_mode" not in database:
    errors.append("EXECUTION_PROVENANCE_MIGRATION_MISSING")

calendar = require("desktop/alikhande/core/calendar_gate.py")
if "coverage_until" not in calendar:
    errors.append("CALENDAR_COVERAGE_GUARD_MISSING")

backtest = require("desktop/alikhande/app/backtest.py")
backtest_view = require("desktop/alikhande/ui/views/backtest.py")
cli = require("desktop/alikhande/__main__.py")
if "run_with_atomic_persistence" not in backtest:
    errors.append("ATOMIC_BACKTEST_ENTRYPOINT_MISSING")
if "evidence_signal_id" not in backtest or "cancelled is not None" not in backtest:
    errors.append("REPLAY_EVIDENCE_ID_OR_CANCEL_POLL_MISSING")
for name, source in (("ui", backtest_view), ("cli", cli)):
    if "run_with_atomic_persistence" not in source:
        errors.append(f"ATOMIC_BACKTEST_NOT_WIRED {name}")
    if "purge_runs_of_kind" in source:
        errors.append(f"PREEMPTIVE_EVIDENCE_PURGE {name}")


print("STATIC VALIDATION")
print(f"INFO python_files={len(list(PACKAGE.rglob('*.py')))}")
print("INFO mql_gate=PASS" if not mql_gate.returncode else "INFO mql_gate=FAIL")
if errors:
    for error in errors:
        print("FAIL", error)
    raise SystemExit(1)
print(
    "PASS governance / MQL5 gate / Python compile / single send / worker boundary / "
    "exact reconciliation / Demo evidence / atomic backtest evidence"
)
