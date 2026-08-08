# GPT v1.3 Integration Closure — 2026-08-08

Status: **STATIC PASS / RUNTIME UNPROVEN**

This closure was triggered by an independent Claude v1.3 audit which correctly identified that several GPT v1.3 modules were unit-tested but unreachable from the production EA.

## Defects reproduced and closed

1. **Dead v1.3 signal modules** — production `Signals/SignalEngine.mqh` now calls `ZoneSemanticsV13`, `ExplainableScoringV13` and `LiveValidatorV13`; production lifecycle calls `LifecycleV13`; `MarketData` uses `RuntimeSnapshots`; `PortfolioRisk` uses `RiskMathV13`; EA uses `NewBarDetector`; NewsGate uses the provenance-aware calendar provider.
2. **Inside-zone blindness** — production zones carry DEMAND/SUPPLY type and price-inside-zone is a first-class relation used by the actual signal path.
3. **Stale quote evaluation** — the EA refreshes closed-bar trend state only when a bar changes, but signal validity / Entry / SL / TP are evaluated every scan pass and the cached UI signal is refreshed even when `signal_id` is unchanged.
4. **Uninitialised scheduler arrays** — alert and new-bar datetime arrays are explicitly initialised after resize.
5. **Uncached indicator handles** — TrendEngine caches EMA50/EMA200/ADX/ATR handles by symbol/timeframe; ZoneEngine caches ATR handles.
6. **Recovery authority** — reconciler now consults current Positions, current Orders, History Deals and History Orders. UNKNOWN remains non-terminal and therefore blocks new sends.
7. **Plan-scoped confirmation** — a preview can execute only while it remains valid and its `signal_id` still matches the current live signal. Confirmation is one-shot.
8. **Calendar context** — unavailable calendar blocks in terminal/demo context; tester/optimization may continue but are explicitly NEWS-BLIND rather than falsely CLEAR.
9. **Architecture documentation drift** — architecture document now describes the actual filesystem and actual production facade relationships.

## Static gate hardening

`tools/static_validate.py` now checks:
- all production `.mqh` modules are reachable through the EA include graph;
- local and project-root include resolution;
- live signal engine wiring;
- stale bar-gated evaluation regression;
- critical runtime array initialisation;
- indicator-handle caching in analysis hot paths;
- exactly one OrderSend boundary;
- UNKNOWN execution remains blocking;
- reconciliation includes Positions, Orders, History Deals and History Orders.

A first run exposed a bug in the gate itself: local includes such as `"Preflight.mqh"` were not resolved. The resolver was corrected before accepting reachability results.

## GitHub evidence

Draft PR: **#5 — GPT v1.3 independent integration candidate**.

Latest static-gate run after integration closure: **PASS**.

Observed gate output on the successful run:
- production modules reachable: **45 / 45**
- include graph: PASS
- live signal path: PASS
- indicator cache checks: PASS
- execution recovery source checks: PASS
- safety policy checks: PASS

## Not established

No MetaEditor compile or MT5 runtime execution has occurred in this environment. Therefore this branch is not compile-qualified, shadow-qualified or demo-qualified yet.

Blocking next evidence:
1. Windows MetaEditor: every configured target `0 errors, 0 warnings`.
2. Run all MQL5 phase self-tests.
3. Duplicate transaction replay inside MT5.
4. Restart reconstruction matrix.
5. Alert-only and Shadow smoke.
6. Controlled Demo Confirm test only after the above pass.
