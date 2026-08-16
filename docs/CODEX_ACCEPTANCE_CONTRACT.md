# Codex Acceptance Contract — Alikhande Scanner v1.3

Status: **MANDATORY / NON-BYPASSABLE**

This document defines what "complete" means. It is intentionally stricter than source review.

## Core rule

**No evidence = no pass.**

Codex must not declare the project COMPLETE, READY, VERIFIED, SAFE FOR DEMO, or 100% working unless every mandatory gate below has passed with saved evidence. A skipped, unavailable, inconclusive, flaky, manually assumed or undocumented test is NOT PASSED.

If a mandatory gate fails, stop the qualification sequence, diagnose and fix the root cause, rerun the failed gate, then rerun all dependent gates.

## G0 — Repository and source integrity

Mandatory:
- work from the current supervised Alikhande v1.3 source; do not silently replace it with another implementation;
- preserve commit history and push after each phase;
- run `python tools/static_validate.py`;
- production reachability must be 100% for intended `.mqh` production modules;
- exactly one `OrderSend` production boundary;
- no `OrderSendAsync`;
- no martingale, grid, recovery or averaging-down logic;
- architecture docs must match the actual filesystem and runtime path;
- repository must be clean at each evidence checkpoint.

Pass evidence:
- static-gate console log;
- commit SHA;
- list of changed files and reason for each change.

## G1 — MetaEditor compile qualification

Use the real Windows MetaEditor. Run `RUN_WINDOWS_GATE.cmd` / `tools/compile_mt5.ps1`.

Mandatory:
- every configured script/test target compiles;
- production EA compiles;
- **0 errors / 0 warnings** on every target;
- save every compiler log under `artifacts/metaeditor/`;
- compiler warnings may not be dismissed as harmless.

Pass evidence:
- MetaEditor logs for all configured targets;
- exact MetaEditor build/version;
- Windows/terminal environment note.

## G2 — MQL5 self-test execution

Actually execute, not merely compile:
- Phase1RuntimeSelfTests;
- Phase2ZoneSignalSelfTests;
- Phase3ScoringLifecycleSelfTests;
- Phase4PersistenceSelfTests;
- Phase5RiskSelfTests;
- Phase6ExecutionSelfTests;
- Phase7CalendarUiSelfTests;
- EvidenceIntegritySelfTests;
- any later test added while fixing defects.

Mandatory:
- every assertion PASS;
- zero unexpected runtime exceptions/errors;
- save terminal Experts/Journal output.

A test that cannot run must be fixed; it cannot be marked skipped-pass.

## G3 — Signal correctness matrix

Prove production behavior, not test-only modules.

Mandatory cases:
1. closed-bar structural facts remain stable inside a bar;
2. current bid/ask can change tradability, Entry, SL and TP without waiting for a new M5 bar;
3. price below demand, inside demand and above demand are distinguished correctly;
4. price below supply, inside supply and above supply are distinguished correctly;
5. inside-zone pullback can form a valid setup when all other rules allow it;
6. stale/no-tick/high-spread conditions veto tradability;
7. score components, penalties and vetoes are visible and deterministic;
8. veto overrides a high score;
9. rule score is never exposed as calibrated probability;
10. signal identity changes when parameter hash or broker-spec identity changes;
11. duplicate signal persistence does not create duplicate evidence;
12. lifecycle rejects illegal transitions and resolves terminal states consistently.

Save inputs and outputs for each case.

## G4 — Persistence and migration matrix

Mandatory:
- fresh database creation to current schema;
- migration v4 -> v5 -> v6 -> v7 using representative legacy databases;
- migration runs transactionally and rollback is verified on injected failure where practical;
- database newer than supported is refused;
- terminal/demo database does not share tester/optimization persistence;
- tester execution cannot contaminate production evidence;
- restart preserves unresolved execution state;
- outcomes preserve evidence source, rule version, scoring version, parameter hash, broker-spec hash and execution id;
- terminal execution without outcome is recovered after restart;
- no migration step may silently redefine an already released schema version.

Optimization behavior must be explicitly verified. If optimization persistence is disabled, prove that no production evidence is written. If isolated, prove uniqueness and cleanup policy.

## G5 — Risk and account-safety matrix

Mandatory:
- real account is unconditionally blocked even if UI/input attempts Demo Confirm;
- invalid account equity fails closed;
- scanner position without SL is unbounded risk and blocks new exposure;
- failed `OrderCalcProfit` fails closed;
- total scanner open-risk cap is deterministic and order-independent;
- foreign/manual positions are handled exactly according to documented policy and never silently mutate scanner consecutive-loss accounting;
- scanner closed-deal loss accounting filters by ownership/magic;
- daily loss, drawdown and consecutive-loss guards persist across restart;
- lot sizing respects min/max/step, tick size/value and broker constraints;
- minimum R:R remains enforced;
- broker specification drift invalidates or revalidates plans safely.

## G6 — Execution safety and idempotency matrix

This is a release-critical gate.

Mandatory:
- `OrderCheck` executes before every allowed send;
- intent is durably persisted before `OrderSend`;
- exactly one send boundary exists;
- real-account send attempt returns blocked without broker submission;
- Demo Confirm requires explicit current plan confirmation;
- plan confirmation is invalid after expiration, signal change, broker-spec change or relevant risk/news change;
- duplicate/replayed `DEAL_ADD` cannot increment `filled_volume` twice;
- duplicate deal ticket remains blocked after EA restart;
- partial fills aggregate correctly;
- order rejected, cancelled and expired states resolve correctly;
- position-active state resolves correctly;
- completed open+close trade resolves correctly;
- manual/foreign deals cannot be correlated to scanner execution;
- same-symbol older scanner trade cannot be stolen by a newer execution;
- correlation uses exact order/position/deal identity;
- `UNKNOWN` is non-terminal and blocks new sends;
- no timeout may turn UNKNOWN into an implicit pass;
- no database deletion is used as a recovery mechanism.

## G7 — Restart / crash reconstruction matrix

Perform controlled restart tests at these points:
1. after intent persisted but before/around send result handling;
2. order accepted but before first deal event is processed;
3. after partial fill;
4. after full fill / active position;
5. after closing deal but before outcome persistence;
6. terminal execution persisted but outcome row not yet written;
7. unresolved/UNKNOWN state.

After each restart, compare SQLite state with:
- current Orders;
- current Positions;
- History Orders;
- History Deals.

Mandatory:
- system reconstructs authoritative state or remains safely UNKNOWN;
- no duplicate order is emitted merely because the EA restarted;
- no evidence row is silently lost or double-created.

## G8 — Economic calendar matrix

Mandatory:
- terminal/demo context uses the live calendar provider;
- high-impact relevant event blocks according to configured before/after window;
- calendar unavailable in terminal/demo fails closed;
- tester/optimization never silently pretends live calendar data existed;
- tester without historical news dataset is explicitly NEWS-BLIND, according to documented policy;
- statistics from NEWS-BLIND runs cannot be confused with fully news-aware production evidence.

## G9 — UI / operator workflow

Manually smoke-test every tab and save screenshots/log notes:
- Overview;
- Signal;
- Risk;
- News;
- History;
- Stats;
- Settings;
- System/Health.

Mandatory:
- no dead buttons/tabs;
- Open Chart opens/reuses according to policy;
- chart overlays match the currently selected signal;
- Signal page shows reasons, penalties/vetoes and states that score is not probability;
- News page shows source/provenance;
- Risk preview shows entry/SL/TP/lot/risk and blocks stale preview;
- Demo execution requires explicit user confirmation;
- System health displays unresolved execution and breaker states;
- UI does not contain hidden trading logic or bypass safety gates.

## G10 — Alert Only and Shadow endurance smoke

Run the EA in real terminal market-data conditions with trading disabled.

Mandatory:
- Alert Only smoke with no order submission;
- Shadow smoke long enough to exercise multiple timer/bar cycles and at least one data refresh/restart cycle;
- no uncontrolled memory/handle growth;
- no repeated indicator handle creation in hot path;
- no database spam caused by identical live signal refresh;
- no repeated alerts violating cooldown;
- no stale UI state after quote movement;
- outcome evidence generated in Shadow is labelled SHADOW only.

Record duration, symbols, terminal logs and relevant DB row counts.

## G11 — Controlled Demo Confirm qualification

Only after G0-G10 PASS.

Demo account only.

Mandatory:
- verify account mode before the test;
- use minimum sensible demo risk/volume allowed by the project/broker;
- capture preview and `OrderCheck` result;
- explicit confirmation;
- observe request -> order -> deal -> position -> close/reconcile lifecycle;
- verify database execution/deal/outcome rows;
- verify no duplicate fill from replayed transaction processing;
- restart once during a controlled unresolved/active state when safe and verify reconstruction;
- confirm final outcome source is DEMO and is correlated to the execution/position.

Do not perform any real-account test.

## G12 — Strategy Tester / historical validity

Software correctness and trading edge are separate gates.

Mandatory before any performance claim:
- use Every Tick Based on Real Ticks where available;
- document symbol/broker specification and test period;
- fixed parameters before OOS evaluation;
- separate in-sample / validation / out-of-sample windows;
- include spread/commission/swap assumptions supported by terminal/broker data;
- report trade count, win rate, profit factor, max drawdown, recovery factor and average R;
- report long/short separately;
- robustness run with increased spread/slippage assumptions where supported;
- no tuning on the final OOS period;
- no probability or profitability claim when sample size/evidence gate is insufficient.

A profitable backtest is not required to prove software quality. If edge fails, report `SOFTWARE QUALIFIED / STRATEGY EDGE NOT PROVEN` rather than hiding the result.

## G13 — Final adversarial review

Before delivery, Codex must perform a fresh red-team audit of its own final tree as though reviewing another developer's code.

Search specifically for:
- unreachable production modules;
- duplicated sources of truth;
- test-only safety properties not wired to EA;
- magic+symbol-only execution correlation;
- hidden fail-open behavior;
- stale quote/plan use;
- array/handle lifecycle issues;
- migration version drift;
- unsafe error swallowing;
- unscoped outcome statistics;
- UI paths that bypass risk/news/execution gates;
- real-account bypass paths;
- code/doc mismatch;
- claims unsupported by runtime evidence.

Every finding must be fixed or explicitly classified with severity and reason for deferral. P0/P1 safety defects cannot be deferred for qualification.

## Required final delivery package

Codex may request final acceptance only after producing:

1. final commit SHA and branch;
2. clean working-tree confirmation;
3. phase-by-phase PASS/FAIL table for G0-G13;
4. MetaEditor 0/0 compiler logs;
5. MQL5 self-test logs;
6. restart/reconciliation test matrix with evidence;
7. Alert/Shadow smoke report;
8. controlled Demo Confirm report;
9. DB migration/evidence report;
10. UI screenshots/verification notes;
11. Strategy Tester/backtest/OOS report or explicit `EDGE NOT PROVEN` status;
12. list of every defect found and its resolution commit;
13. known limitations and anything not tested;
14. explicit statement: **NO REAL-ACCOUNT EXECUTION WAS PERFORMED**.

## Final status vocabulary

Only these status labels are allowed:
- `BLOCKED` — mandatory gate cannot run or has failed;
- `STATIC_CANDIDATE` — source/static gates only;
- `COMPILE_QUALIFIED` — real MetaEditor 0/0 achieved;
- `RUNTIME_QUALIFIED` — self-tests + restart + smoke gates passed;
- `DEMO_QUALIFIED` — controlled demo execution gate passed;
- `STRATEGY_EDGE_NOT_PROVEN` — software may be qualified but statistical edge is not established;
- `OOS_EVIDENCE_AVAILABLE` — OOS evidence exists and is reported without overstating certainty.

The phrase `100% complete` is forbidden as a technical claim. The closest acceptable delivery statement is: **"All mandatory acceptance gates executed and passed; no known P0/P1 defects remain; limitations are documented."**
