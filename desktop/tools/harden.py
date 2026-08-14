#!/usr/bin/env python3
"""The three-stage hardening loop: AUDIT → FIX → VERIFY.

Run one cycle:

    python3 tools/harden.py            # audit and verify, report only
    python3 tools/harden.py --stage audit
    python3 tools/harden.py --stage verify

The loop exists because "make sure the robot has no weaknesses" is not a task
that finishes — it is a cadence. Each stage has an explicit gate, and a stage
only passes when its gate does:

**AUDIT** — machine-checkable weaknesses. Not style: each check below
corresponds to a defect class that has actually bitten this codebase, and the
comment on each says which. A finding is a fact about the source, not an
opinion about it.

**FIX** — deliberately NOT automated. Every serious defect this project has hit
(the inverted stop, the deal replay, the unbounded position, the released
submit gate) needed a judgement about *what the right behaviour is*, and a tool
that rewrites code to satisfy a checker optimises for the checker. This stage
prints what to fix and stops.

**VERIFY** — the gates that must hold before anything ships: both test paths
(with and without Qt, because the dependency-free run is what keeps the core
dependency-free), the MQL5 static gate, and a backtest whose arithmetic
reconciles.

Exit code is 0 only when every stage that ran passed, so this drops into CI or
a scheduled job unchanged.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "alikhande"
REPO = ROOT.parent


@dataclass
class Finding:
    severity: str  # P0 | P1 | P2
    area: str
    detail: str
    where: str = ""


@dataclass
class StageResult:
    name: str
    passed: bool
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ============================================================== stage 1: audit


def _python_files() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def check_core_has_no_external_imports() -> list[Finding]:
    """The property the whole architecture rests on.

    If ``core`` grows an import of PySide6, MetaTrader5 or sqlite3, the entire
    pipeline stops being testable without those installed — which is how the
    MQL5 build ended up unverifiable in the first place.
    """
    forbidden = ("PySide6", "MetaTrader5", "sqlite3", "numpy", "pandas")
    findings = []
    for path in (PACKAGE / "core").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(name.split(".")[0] == bad for bad in forbidden):
                    findings.append(
                        Finding(
                            "P0",
                            "core purity",
                            f"core imports {name} — the pure core must stay "
                            "runnable and testable with nothing installed",
                            f"core/{path.name}:{node.lineno}",
                        )
                    )
    return findings


def check_single_order_boundary() -> list[Finding]:
    """Exactly one module may send an order."""
    call = re.compile(r"\bsend_order\s*\(")
    allowed = {"core/execution.py", "core/ports.py"}
    findings = []
    for path in _python_files():
        relative = path.relative_to(PACKAGE).as_posix()
        if relative in allowed or relative.startswith("adapters/"):
            continue
        if call.search(path.read_text(encoding="utf-8")):
            findings.append(
                Finding("P0", "order boundary", "calls send_order", relative)
            )
    return findings


def check_forbidden_strategies() -> list[Finding]:
    """Martingale, grid, recovery and averaging down are out of scope by policy.

    Checked by name because these arrive as a "small improvement" long after
    everybody has forgotten the rule.
    """
    patterns = {
        "martingale": r"\bmartingale\b",
        "grid trading": r"\bgrid_(?:trade|step|level)\b",
        "averaging down": r"\baverage_down\b|\baveraging_down\b",
        "recovery sizing": r"\brecovery_(?:lot|multiplier|factor)\b",
    }
    findings = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8").lower()
        for name, pattern in patterns.items():
            if re.search(pattern, source):
                findings.append(
                    Finding(
                        "P0",
                        "forbidden strategy",
                        f"{name} pattern present",
                        path.relative_to(PACKAGE).as_posix(),
                    )
                )
    return findings


def check_unknown_is_never_auto_terminal() -> list[Finding]:
    """The P0 that released the submit gate.

    A state meaning "not resolved" must never be recordable as finished.
    """
    source = (PACKAGE / "core" / "execution.py").read_text(encoding="utf-8")
    findings = []
    if "AS_EXEC_UNKNOWN" in source or "ExecState.UNKNOWN" not in source:
        findings.append(
            Finding("P1", "reconciliation", "UNKNOWN handling changed shape", "core/execution.py")
        )
    match = re.search(
        r"def may_be_auto_terminal.*?return (.*?)\n\n", source, re.DOTALL
    )
    if match and "UNKNOWN" in match.group(1):
        findings.append(
            Finding(
                "P0",
                "reconciliation",
                "UNKNOWN is listed as auto-terminal — an unresolved execution "
                "would release the submit gate",
                "core/execution.py",
            )
        )
    return findings


def check_ui_does_not_touch_engine_privates() -> list[Finding]:
    findings = []
    for path in (PACKAGE / "ui").rglob("*.py"):
        for match in re.finditer(r"_engine\.(_\w+)", path.read_text(encoding="utf-8")):
            findings.append(
                Finding(
                    "P2",
                    "layering",
                    f"UI reads engine private {match.group(1)}",
                    path.relative_to(PACKAGE).as_posix(),
                )
            )
    return findings


def check_translation_completeness() -> list[Finding]:
    """Every user-visible string must exist in both languages, with matching
    placeholders."""
    sys.path.insert(0, str(ROOT))
    from alikhande.i18n import EN, FA  # noqa: PLC0415 - deliberate late import

    findings = []
    for key in sorted(set(EN) - set(FA)):
        findings.append(Finding("P1", "i18n", f"missing Persian key {key}"))
    for key in sorted(set(FA) - set(EN)):
        findings.append(Finding("P2", "i18n", f"orphan Persian key {key}"))

    placeholder = re.compile(r"\{(\w+)\}")
    for key in sorted(set(EN) & set(FA)):
        if sorted(placeholder.findall(EN[key])) != sorted(placeholder.findall(FA[key])):
            findings.append(Finding("P1", "i18n", f"placeholder mismatch on {key}"))
    return findings


def check_untranslated_ui_literals() -> list[Finding]:
    """Human-readable literals in the views that never reach ``t()``.

    Heuristic by nature, so it reports P2: a sentence-shaped string assigned to
    something the operator reads is *probably* an untranslated leak, and a
    couple of false positives are cheaper than a Persian screen with English
    scattered through it.
    """
    findings = []
    sentence = re.compile(r"^[A-Z][a-z]+(?: [A-Za-z0-9,'—/\.\-]+){2,}$")
    setters = re.compile(r"\.(setText|setToolTip|setPlaceholderText)\(\s*[\"']([^\"']{12,})[\"']")
    for path in (PACKAGE / "ui" / "views").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for match in setters.finditer(source):
            text = match.group(2)
            if sentence.match(text):
                findings.append(
                    Finding(
                        "P2",
                        "i18n",
                        f"untranslated literal: {text[:52]}…",
                        path.relative_to(PACKAGE).as_posix(),
                    )
                )
    return findings


def check_paint_handlers_guard_empty_input() -> list[Finding]:
    """A ``paintEvent`` that raises on empty data takes its whole view down.

    Only handlers that actually paint from a COLLECTION are required to guard.
    Its first run flagged ScoreRing and RiskMeter, both of which paint scalars
    with safe defaults and have no empty input to check — the check was wrong,
    not the code. Narrowing it here rather than deleting it keeps the finding
    that matters (a chart iterating an empty series) and drops the noise.
    """
    findings = []
    iterates = re.compile(r"for\s+\w+(?:,\s*\w+)*\s+in\s+(?:enumerate\()?self\.(_\w+)")
    measures = re.compile(r"(?:len|min|max|sum)\(\s*self\.(_\w+)")
    subscripts = re.compile(r"self\.(_\w+)\s*\[")

    for name in ("charts.py", "components.py"):
        path = PACKAGE / "ui" / name
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.FunctionDef) and node.name == "paintEvent"):
                continue
            body = ast.get_source_segment(source, node) or ""

            paints_collection = (
                iterates.search(body) or measures.search(body) or subscripts.search(body)
            )
            if not paints_collection:
                continue

            # Any early return, emptiness test or length comparison counts.
            guarded = re.search(
                r"if\s+(not\s+self\.\w+|len\(|self\.\w+\s*(?:<|==)|\w+\s*<)", body
            )
            if not guarded:
                findings.append(
                    Finding(
                        "P1",
                        "robustness",
                        f"paintEvent iterates self.{paints_collection.group(1)} "
                        "with no empty-input guard",
                        f"ui/{name}:{node.lineno}",
                    )
                )
    return findings


def check_probability_is_never_faked() -> list[Finding]:
    """A win rate must never be rendered below the sample floor."""
    source = (PACKAGE / "core" / "statistics.py").read_text(encoding="utf-8")
    findings = []
    if "min_outcome_sample" not in source:
        findings.append(
            Finding("P0", "evidence", "sample floor no longer consulted", "core/statistics.py")
        )
    if "has_historical_estimate" not in source:
        findings.append(
            Finding("P0", "evidence", "estimate flag missing", "core/statistics.py")
        )
    return findings


AUDIT_CHECKS = (
    ("core purity", check_core_has_no_external_imports),
    ("order boundary", check_single_order_boundary),
    ("forbidden strategies", check_forbidden_strategies),
    ("reconciliation", check_unknown_is_never_auto_terminal),
    ("evidence honesty", check_probability_is_never_faked),
    ("translations", check_translation_completeness),
    ("untranslated literals", check_untranslated_ui_literals),
    ("paint guards", check_paint_handlers_guard_empty_input),
    ("layering", check_ui_does_not_touch_engine_privates),
)


def stage_audit() -> StageResult:
    findings: list[Finding] = []
    for name, check in AUDIT_CHECKS:
        try:
            found = check()
        except Exception as error:
            findings.append(Finding("P1", name, f"check itself failed: {error}"))
            continue
        findings.extend(found)

    blocking = [f for f in findings if f.severity in ("P0", "P1")]
    return StageResult("AUDIT", passed=not blocking, findings=findings)


# ================================================================ stage 2: fix


def stage_fix(findings: list[Finding]) -> StageResult:
    """Report what to fix. Deliberately does not fix it.

    Every serious defect this project has hit needed a judgement about what the
    right behaviour *is* — an inverted stop is not a formatting problem. A tool
    that rewrote code until the checks passed would be optimising for the
    checks, which is the failure mode the checks exist to prevent.
    """
    if not findings:
        return StageResult("FIX", passed=True, notes=["nothing to fix"])
    return StageResult(
        "FIX",
        passed=False,
        findings=findings,
        notes=[
            f"{len(findings)} finding(s) need a human decision — see the list above",
            "fix the behaviour, not the check",
        ],
    )


# ============================================================= stage 3: verify


def _run(command: list[str], cwd: Path, env: dict | None = None) -> tuple[bool, str]:
    import os

    merged = dict(os.environ)
    merged.setdefault("QT_QPA_PLATFORM", "offscreen")
    if env:
        merged.update(env)
    try:
        completed = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=1800, env=merged
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    output = (completed.stdout + completed.stderr).strip().splitlines()
    return completed.returncode == 0, "\n".join(output[-4:])


def stage_verify(quick: bool = False) -> StageResult:
    result = StageResult("VERIFY", passed=True)

    checks = [
        ("tests (with Qt)", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], ROOT),
        ("tests (no Qt)", [sys.executable, str(ROOT / "tools" / "noqt_runner.py")], ROOT),
    ]
    if (REPO / "tools" / "static_gate.py").exists():
        checks.append(("MQL5 static gate", [sys.executable, "tools/static_gate.py"], REPO))
        checks.append(("gate self-tests", [sys.executable, "tools/test_static_gate.py"], REPO))
    if not quick:
        checks.append(
            (
                "backtest reconciles",
                [
                    sys.executable, "-m", "alikhande", "backtest",
                    "--symbols", "EURUSD", "--h4-bars", "500",
                    "--warmup", "9900", "--steps", "1200",
                ],
                ROOT,
            )
        )

    for name, command, cwd in checks:
        ok, tail = _run(command, cwd)
        result.notes.append(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            result.passed = False
            result.findings.append(Finding("P0", "verify", f"{name} failed:\n{tail}"))
    return result


# ===================================================================== driver


def render(results: list[StageResult]) -> str:
    lines = ["", "=" * 74, "  ALIKHANDE HARDENING LOOP", "=" * 74]
    for result in results:
        lines.append("")
        lines.append(f"  {result.name}  —  {'PASS' if result.passed else 'FAIL'}")
        lines.append("  " + "-" * 70)
        for note in result.notes:
            lines.append(f"    {note}")
        if result.findings:
            for severity in ("P0", "P1", "P2"):
                group = [f for f in result.findings if f.severity == severity]
                if not group:
                    continue
                lines.append(f"    {severity}  ({len(group)})")
                for finding in group:
                    where = f"  [{finding.where}]" if finding.where else ""
                    lines.append(f"      · {finding.area}: {finding.detail}{where}")
        elif result.name == "AUDIT":
            lines.append("    no findings")

    overall = all(r.passed for r in results)
    lines.append("")
    lines.append("=" * 74)
    lines.append(f"  RESULT: {'PASS' if overall else 'FAIL'}")
    lines.append("=" * 74)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Three-stage hardening loop")
    parser.add_argument(
        "--stage",
        choices=("audit", "fix", "verify", "all"),
        default="all",
        help="run one stage, or all three",
    )
    parser.add_argument(
        "--quick", action="store_true", help="skip the backtest in VERIFY"
    )
    args = parser.parse_args(argv)

    results: list[StageResult] = []
    audit: StageResult | None = None

    if args.stage in ("audit", "fix", "all"):
        audit = stage_audit()
        results.append(audit)

    if args.stage in ("fix", "all") and audit is not None:
        blocking = [f for f in audit.findings if f.severity in ("P0", "P1")]
        results.append(stage_fix(blocking))

    # VERIFY runs even when AUDIT failed. Knowing whether the suite still
    # passes is part of deciding how urgent a finding is.
    if args.stage in ("verify", "all"):
        results.append(stage_verify(quick=args.quick))

    print(render(results))
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
