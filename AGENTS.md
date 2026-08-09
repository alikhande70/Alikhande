# Agent instructions

This repository is governed by `.ai/PROJECT_DIRECTOR.md`, `.ai/PROJECT_DIRECTOR_V1.3.md`, `docs/PROJECT_CONSTITUTION.md`, and `docs/CODEX_ACCEPTANCE_CONTRACT.md`.

## Non-bypassable completion rule

No coding agent may describe Alikhande Scanner as COMPLETE, READY, VERIFIED, SAFE FOR DEMO, or 100% working until every mandatory gate in `docs/CODEX_ACCEPTANCE_CONTRACT.md` has produced real evidence.

A skipped, unavailable, inconclusive, flaky, manually assumed, or undocumented test counts as **NOT PASSED**. Fix the cause or leave the project status blocked. Never convert missing evidence into a pass.

When changing MQL5 code:
- keep trading submission isolated to `Execution/ExecutionEngine.mqh`;
- preserve unconditional real-account hard block and demo-only execution;
- preserve `OrderCheck` before the single `OrderSend` boundary;
- preserve persistent deal idempotency and event-driven `OnTradeTransaction` reconciliation;
- keep UNKNOWN execution non-terminal and blocking until authoritative broker evidence resolves it;
- use closed-bar information for structural signal facts and current quote for live validation;
- persist identities/state before relying on in-memory caches;
- keep Shadow evidence separate from broker-derived Demo evidence;
- never label rule scores as probability;
- never delete/replace the runtime database merely to clear an unresolved execution;
- run `python tools/static_validate.py` before every push;
- report MetaEditor compilation as NOT VERIFIED unless real compiler logs exist;
- report runtime tests as NOT VERIFIED unless terminal/tester logs or durable evidence exist;
- make no profitability/edge claim without backtest + OOS evidence.

Codex must work phase-by-phase, commit/push after each passed phase, and stop on the first failed mandatory gate until the defect is fixed and the failed test is rerun.
