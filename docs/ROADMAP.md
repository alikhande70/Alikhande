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
- [ ] Import exact v1.1.0 source and wire the new modules into `AlikhandeScanner.mq5` —
      **blocked**, see `docs/ARCHITECTURE_V1.2.md` "known gap"
- [ ] `CompileAllModules.mq5` updated to include every new header
- [ ] Compile-clean in MetaEditor (0 errors / 0 warnings) — cannot be verified in this
      environment; no MetaEditor/MT5 terminal available here. Must be checked by the user or in
      a Windows/Wine MT5 environment before this is considered done.
- [ ] Acceptance tests re-run against `docs/ACCEPTANCE_TESTS.md` plus new P0 gates

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
