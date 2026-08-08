# Changelog

> **Status note:** the `Analysis/`, `Signals/`, `Trading/`, `Broker/`, `Safety/`,
> `Storage/SignalLogger.mqh`, `Statistics/`, and `Core/{Config,SignalRegistry,Hash,
> NewBarDetector}.mqh` files plus `Experts/AlikhandeScanner/AlikhandeScanner.mq5` in this branch
> are a **provisional, docs-based rewrite** and are NOT the v1.1.0 baseline. The real
> `alikhande_scanner_v1.1.0.zip` source has been separately retrieved and SHA-256-verified against
> `MANIFEST.sha256` in another session. That real source is the actual integration base — these
> provisional files stay on this branch for reference only until the real source is merged in and
> audited against them (see `docs/ROADMAP.md` task "Get real v1.1.0 source, then audit+merge").
> The P0 modules (`Storage/Database.mqh`, `Domain/SignalLifecycle.mqh`, `Execution/*`, `Risk/*`,
> `News/*`, `Health/*`, `UI/DashboardTabs.mqh`, `Tests/*`) are unaffected — they're additive and
> don't depend on which engine implementation they sit on top of.

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

Follow-up pass: since the exact v1.1.0 binary could not be transferred through this session's
chat channel (confirmed unreliable at 37KB after two attempts), the core engines were rewritten
from scratch to match the documented v1.1.0 behavior instead — `Analysis/TrendEngine.mqh`,
`Analysis/ZoneEngine.mqh`, `Signals/SignalEngine.mqh`, `Trading/RiskPlanner.mqh`,
`Trading/DemoExecution.mqh`, `Broker/SymbolResolver.mqh`, `Broker/SymbolSpec.mqh`, `Safety/*`,
`Storage/SignalLogger.mqh`, `Statistics/Statistics.mqh`, `Core/{Config,SignalRegistry,Hash,
NewBarDetector}.mqh`, `Domain/{Enums,Models}.mqh`, and `Experts/AlikhandeScanner/
AlikhandeScanner.mq5` itself (wiring every module together, sliced scanner, OnTradeTransaction
reconciliation). See `docs/v1.1.0_README.md` and `docs/v1.1.0_ACCEPTANCE_TESTS.md` for the
behavior this was built against.

Known incompleteness (tracked in `docs/ROADMAP.md`): the interactive Preview/Confirm-to-execute
dashboard UI is not wired yet, and `Safety/AccountRiskGuard.mqh` isn't called from the execution
path yet. No MetaEditor/MT5 terminal is available in this environment, so **nothing here has been
compiled or run** — every module should be treated as "believed correct, not proven to compile"
until checked in a real MT5 environment.

## v1.1.0 — ScannerPanel Hardening Edition

See `docs/` for the v1.1.0 README/ACCEPTANCE_TESTS content pulled from the Google Drive release
package.
