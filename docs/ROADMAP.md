# Alikhande Scanner — Roadmap

Adopted from the modernization research discussion, with three adjustments after independent
verification against official MQL5 documentation (see commit history / conversation for the
full research trail):

1. Dashboard tabs are native chart objects, not `CCanvas` bitmaps (CPU-budget reasoning).
2. Added symbol/broker-spec drift detection as a P0 item (not in the original list).
3. News gate in v1.2.0 is live-only (`CalendarValueHistory`); the static historical dataset for
   Strategy Tester backtesting is deferred to P2 so it doesn't slow down P0 execution work.

## v1.2.0 — Reliability & Evidence (this pass)

No new strategies or setups. Scope:

- [x] SQLite persistence (`Storage/Database.mqh`)
- [x] Signal Lifecycle state machine (`Domain/SignalLifecycle.mqh`)
- [x] Execution reliability: `TradeRequestTracker`, `ExecutionStateMachine`, `OrderPreflight`
- [x] Portfolio risk gates (`Risk/PortfolioRisk.mqh`)
- [x] News gate, P0 scope (`News/NewsFilter.mqh`)
- [x] System health: restart recovery, telemetry, broker-spec drift (`Health/SystemHealth.mqh`)
- [x] Multi-tab dashboard (`UI/DashboardTabs.mqh`)
- [x] Unit test skeleton (`Tests/*`)
- [x] Exact v1.1.0 binary import abandoned (chat-channel transfer unreliable at 37KB, confirmed
      after two attempts). Replaced with a fresh, spec-compliant reimplementation of every core
      engine (`Analysis/TrendEngine.mqh`, `Analysis/ZoneEngine.mqh`, `Signals/SignalEngine.mqh`,
      `Trading/RiskPlanner.mqh`, `Trading/DemoExecution.mqh`, `Broker/SymbolResolver.mqh`,
      `Broker/SymbolSpec.mqh`, `Safety/*`, `Storage/SignalLogger.mqh`, `Statistics/Statistics.mqh`,
      `Core/SignalRegistry.mqh`, `Core/Config.mqh`), matching the documented v1.1.0 behavior from
      `docs/v1.1.0_README.md` / `docs/v1.1.0_ACCEPTANCE_TESTS.md` line-for-line where testable.
- [x] `Experts/AlikhandeScanner/AlikhandeScanner.mq5` wired end-to-end: OnInit resolves symbols,
      warms up specs, opens the DB, recovers restart state; OnTimer runs the sliced scanner
      (data quality -> news gate -> MTF/zones -> setup -> score -> signal persistence ->
      dashboard); OnTradeTransaction reconciles fills.
- [x] `CompileAllModules.mq5` updated to include every header (new + engine)
- [ ] **Known incompleteness**: the interactive Preview/Confirm-to-execute UI is not wired yet.
      `Trading/DemoExecution.mqh::ExecuteDemoTrade` and the full Execution/Risk/Guard pipeline
      behind it are complete and callable, but no dashboard button currently drives a signal from
      `CONFIRMED` through `PREVIEWED` to an actual `OrderSend`. `Safety/AccountRiskGuard.mqh`'s
      `EvaluateAccountGuards` is likewise implemented but not yet called from the execution path.
      This is the next slice of work.
- [ ] Compile-clean in MetaEditor (0 errors / 0 warnings) — **cannot be verified in this
      environment**; no MetaEditor/MT5 terminal is available in this remote session. A brace-
      balance sanity check passed on every file, but that is not a substitute for an actual
      compile. Must be checked by the user (or in a future session with MT5/Wine access) before
      this is considered done — treat every module as "believed correct, not proven to compile"
      until then.
- [ ] Acceptance tests re-run against `docs/v1.1.0_ACCEPTANCE_TESTS.md` plus the new v1.2.0 gates
      listed at the bottom of that file — needs a live/demo MT5 terminal, not available here.

## v1.3.0 — Signal Intelligence (next)

- Market Regime Engine (ADX + ATR percentile + EMA structure + H4/H1 alignment + spread
  percentile + session — not 20 indicators)
- Score versioning tied to `rule_version`
- Session-aware scoring
- Historical Probability, computed only from `outcomes` table — never fabricated
- Wilson confidence interval on probability (small-sample honesty)
- Expectancy, MFE/MAE tracking
- Walk-Forward Analysis + Walk-Forward Efficiency
- Monte Carlo on trade sequence (path dependency)
- Parameter stability / plateau analysis
- News gate P2: static historical dataset (MQL5 resource) for realistic tester backtesting

## v2.0 — Statistical Intelligence (only if v1.3 produced enough data)

- Feature store (built from `signal_features` accumulated since v1.2.0)
- Meta-labeling as a second layer on top of the existing rule engine (accept/reject, not a
  replacement)
- ONNX inference (MT5 build from Jan 2026 supports CUDA + in-Tester validation — technical
  readiness is not the blocker; a validated Outcome dataset is)
- Probability calibration, model versioning, champion/challenger, drift detection

## Explicitly out of scope (any version, unless revisited)

More indicators/setups without evidence they help, Martingale/Grid/Recovery sizing, direct
AI BUY/SELL output, DOM/Iceberg as a core dependency, Telegram/external webhooks in the core EA
(`WebRequest` is synchronous and unsupported in the Strategy Tester), fabricated historical
probability, optimizer-driven "best profit factor" parameter search without walk-forward/Monte
Carlo validation.

## Register of previously-missing items (tracked so they don't get silently dropped again)

| Item | Status |
|---|---|
| Persistent Signal Registry | v1.2.0 (`Storage/Database.mqh`) |
| Restart Recovery | v1.2.0 (`Health/SystemHealth.mqh`, `TradeRequestTracker.mqh`) |
| Execution Reconciliation | v1.2.0 (`Execution/ExecutionStateMachine.mqh`) |
| Portfolio/Currency Exposure | v1.2.0 (`Risk/PortfolioRisk.mqh`) |
| News/Calendar State | v1.2.0, P0 scope (`News/NewsFilter.mqh`) |
| Database Schema Version | v1.2.0 (`Core/VersionInfo.mqh`, `schema_meta` table) |
| Parameter Snapshot per Signal | v1.2.0 (`Core/ParameterHash.mqh`) |
| Rule Version per Signal | v1.2.0 (`Core/VersionInfo.mqh`) |
| Broker Spec Snapshot + Drift Detection | v1.2.0 (`Health/SystemHealth.mqh`) — added, not in original list |
| Session/DST handling | v1.3.0 |
| Signal Expiration | v1.2.0 (`SIGNAL_EXPIRED` state) |
| MFE/MAE tracking | v1.3.0 |
| Calibration/Brier Score | v2.0 |
| Walk-Forward | v1.3.0 |
| Monte Carlo | v1.3.0 |
| Parameter Stability | v1.3.0 |
| Health Monitor | v1.2.0 (`Health/SystemHealth.mqh`) |
| Runtime performance telemetry | v1.2.0 |
| Alert deduplication | v1.2.0 (Health tab counter; enforcement lives in `SignalRegistry.mqh` once imported) |
| Release rollback | not started — needs a decision on whether this repo or MT5's own update mechanism owns it |
| Dependency/license register | tracked in `docs/ARCHITECTURE_V1.2.md` section 10 |
