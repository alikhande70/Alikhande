# Changelog

## v1.2.0 — Reliability & Evidence Edition (in progress)

Added (net-new modules, additive to the v1.1.0 engines):

- `Storage/Database.mqh` — SQLite persistence layer (signals, trade lifecycle, outcomes,
  symbol specs, news events, parameter sets, runtime events, system health), transaction-wrapped
  writes.
- `Domain/SignalLifecycle.mqh` — explicit signal state machine with an allow-listed transition
  table (CANDIDATE → CONFIRMED → PREVIEWED → ACTIVE → {TP, SL, EXPIRED, INVALIDATED, AMBIGUOUS,
  NOT_FILLED}).
- `Execution/TradeRequestTracker.mqh`, `ExecutionStateMachine.mqh`, `OrderPreflight.mqh` —
  SignalID → TradePlanID → RequestID → DealID tracking, idempotent request creation, an
  `OnTradeTransaction` handler that never assumes event ordering (per MetaQuotes documentation),
  restart recovery, stale-request reconciliation, and a standardized pre-`OrderSend` pipeline
  (`OrderCheck`, `SetTypeFillingBySymbol`, stops/freeze-level/lot validation).
- `Risk/PortfolioRisk.mqh` — per-trade, per-symbol, total-open, currency-exposure, and
  daily-risk-budget gates; blocks outright rather than silently resizing.
- `News/NewsFilter.mqh` — currency-aware, live `CalendarValueHistory`-based `BLOCK_NEW_SIGNAL`
  gate (P0 scope; historical static dataset for Strategy Tester backtesting deferred to v1.3).
- `Health/SystemHealth.mqh` — restart-recovery marker, CPU-budget telemetry, tick-staleness
  check, and symbol/broker-spec drift detection (hash-based; not in the original proposal).
- `UI/DashboardTabs.mqh` — multi-tab control panel (Overview / Detail / Risk / News / Health)
  built from native chart objects, replacing the single-tab `Dashboard.mqh`.
- `Tests/` — dependency-free unit test harness and coverage for the pure-function parts of the
  new modules, runnable via `Scripts/AlikhandeScanner/RunAllTests.mq5`.
- `Core/VersionInfo.mqh` bumped to 1.2.0 with a DB schema version and rule version.
- `Core/ParameterHash.mqh` — hashes the active scoring parameter set for signal snapshots.
- `docs/ARCHITECTURE_V1.2.md`, `docs/ROADMAP.md`.

Known gap: the v1.1.0 engines themselves (`Analysis/TrendEngine.mqh`, `Analysis/ZoneEngine.mqh`,
`Signals/SignalEngine.mqh`, `Trading/RiskPlanner.mqh`, `Trading/DemoExecution.mqh`,
`Broker/SymbolResolver.mqh`, `Broker/SymbolSpec.mqh`, `UI/Dashboard.mqh`, and
`Experts/AlikhandeScanner/AlikhandeScanner.mq5` itself) have not yet been imported into this
repository — see `docs/ARCHITECTURE_V1.2.md`. Compilation and the acceptance-test gate cannot be
verified until that import happens and MetaEditor is run against the result.

## v1.1.0 — ScannerPanel Hardening Edition

See `docs/` for the v1.1.0 README/ACCEPTANCE_TESTS content pulled from the Google Drive release
package.
