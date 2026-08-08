# Alikhande Scanner — v1.2.0 Architecture Blueprint (Reliability & Evidence)

Status: DRAFT — plan produced from the v1.1.0 spec (README, ACCEPTANCE_TESTS, MANIFEST)
retrieved from Google Drive. The v1.1.0 *source code itself* (the `.mq5`/`.mqh` files inside
`alikhande_scanner_v1.1.0.zip`) could not be transferred into this repository through the
chat/tool channel available in this session — binary round-tripping at that size was not
reliable and a corrupted transcription is worse than no transcription. Two ways to close this
gap:

1. Push the v1.1.0 source directly to this branch (`git push`), or
2. Point this session at a git-clonable location for it (a repo, a raw HTTPS URL, a gist).

Everything below assumes the v1.1.0 modules retain their current responsibilities; new P0
modules are additive and integrate with them by contract (function signatures / file paths),
not by rewriting them.

## 1. Old pipeline vs new pipeline

Old (v1.1.0):

```
Market Data -> H4/H1/M15/M5 -> Zones -> Setup -> Score -> Dashboard
```

New (v1.2.0):

```
Broker/Data Layer
  -> Data Quality + Session + News Gate
  -> Market Regime Engine            [v1.3]
  -> MTF Analysis + Zones            (existing)
  -> Setup Engines                   (existing)
  -> Rule Score                      (existing)
  -> Risk & Portfolio Exposure Gates [NEW]
  -> Signal Lifecycle                [NEW]
  -> Preview
  -> Demo Execution
  -> OnTradeTransaction Reconciliation [NEW]
  -> SQLite Outcome Database         [NEW]
  -> Statistics / Probability        [v1.3, real Outcome-backed]
  -> Dashboard (multi-tab) + Notifications [NEW]
```

v1.3 items are noted but **not built in this pass** — v1.2.0 adds zero new strategies/setups.

## 2. File-by-file disposition

Legend: **KEEP** = unchanged contract, **EXTEND** = same file, new responsibilities added,
**NEW** = introduced in v1.2.0.

| Path | Status | Notes |
|---|---|---|
| `Experts/AlikhandeScanner/AlikhandeScanner.mq5` | EXTEND | wire in Database init, ExecutionStateMachine, PortfolioRisk, NewsFilter, DashboardTabs, SystemHealth |
| `Include/.../Core/Config.mqh` | EXTEND | add `RuleVersion`, DB path, News/Risk toggles |
| `Include/.../Core/Hash.mqh` | KEEP | reused for ParameterHash + BrokerSpecHash |
| `Include/.../Core/NewBarDetector.mqh` | KEEP | |
| `Include/.../Core/SignalRegistry.mqh` | EXTEND | becomes the in-memory mirror of `signals` table |
| `Include/.../Core/VersionInfo.mqh` | EXTEND | bump to 1.2.0, add schema version constant |
| `Include/.../Core/ParameterHash.mqh` | **NEW** | hashes active input set for signal snapshots |
| `Include/.../Storage/SignalLogger.mqh` | EXTEND | CSV becomes an *export*, not the source of truth |
| `Include/.../Storage/Database.mqh` | **NEW** | SQLite schema + prepared-statement helpers |
| `Include/.../Domain/Enums.mqh` | EXTEND | add `SIGNAL_STATE`, `EXEC_STATE` enums |
| `Include/.../Domain/Models.mqh` | EXTEND | add `SignalRecord`, `TradeRequestRecord` structs |
| `Include/.../Domain/SignalLifecycle.mqh` | **NEW** | state machine transition rules |
| `Include/.../Execution/TradeRequestTracker.mqh` | **NEW** | SignalID -> TradePlanID -> RequestID -> DealID map, idempotency |
| `Include/.../Execution/ExecutionStateMachine.mqh` | **NEW** | `OnTradeTransaction` handler, partial fill / requote / unknown handling |
| `Include/.../Execution/OrderPreflight.mqh` | **NEW** | revalidation pipeline + `OrderCheck` + `SetTypeFillingBySymbol` |
| `Include/.../Broker/SymbolResolver.mqh` | KEEP | |
| `Include/.../Broker/SymbolSpec.mqh` | EXTEND | add spec hashing + drift detection (see below) |
| `Include/.../Analysis/TrendEngine.mqh` | KEEP | v1.3 adds Regime on top, not a rewrite |
| `Include/.../Analysis/ZoneEngine.mqh` | KEEP | |
| `Include/.../Signals/SignalEngine.mqh` | EXTEND | must emit a full feature snapshot per signal for `signal_features` |
| `Include/.../Trading/RiskPlanner.mqh` | EXTEND | must consult `Risk/PortfolioRisk.mqh` before accepting a plan |
| `Include/.../Trading/DemoExecution.mqh` | EXTEND | routed through `OrderPreflight` + `TradeRequestTracker` |
| `Include/.../Risk/PortfolioRisk.mqh` | **NEW** | per-symbol/currency/asset-class exposure gates |
| `Include/.../News/NewsFilter.mqh` | **NEW** | `CalendarValueHistory`-based gate (P0), static dataset deferred to P2 |
| `Include/.../Safety/AccountRiskGuard.mqh` | KEEP | |
| `Include/.../Safety/TradeGuards.mqh` | KEEP | |
| `Include/.../Statistics/Statistics.mqh` | EXTEND (v1.3) | becomes Outcome-backed, not touched in v1.2.0 beyond read hooks |
| `Include/.../UI/Dashboard.mqh` | **REPLACED** by `UI/DashboardTabs.mqh` | multi-tab, Overview/Detail/Risk/News/Health, explainability panel |
| `Include/.../Health/SystemHealth.mqh` | **NEW** | restart recovery marker, runtime telemetry, dedup |
| `Include/.../Tests/*` | **NEW** | `TradeRequestTrackerTests.mqh`, `SignalLifecycleTests.mqh`, `PortfolioRiskTests.mqh` (MQL5Unit-style, no external dependency) |
| `Scripts/AlikhandeScanner/CompileAllModules.mq5` | EXTEND | include new headers so MetaEditor parses everything |
| `Scripts/.../SymbolDiscovery.mq5`, `SymbolSpec.mq5` | KEEP | |

## 3. New SQLite schema (`alikhande.sqlite`)

```
signals(signal_id PK, ts, symbol, direction, setup, h4_state, h1_state, m15_state, m5_state,
        spread, atr, support, resistance, entry, sl, tp, long_score, short_score,
        rule_version, parameter_hash, broker_spec_hash, state, created_at)
signal_features(signal_id FK, feature_name, feature_value)
trade_plans(plan_id PK, signal_id FK, risk_pct, lot, sl_price, tp_price, created_at)
trade_requests(request_id PK, plan_id FK, submitted_at, state)
deals(deal_id PK, request_id FK, position_id, volume, price, ts)
outcomes(signal_id FK, result, mfe, mae, closed_at)
symbol_specs(symbol PK, digits, contract_size, stops_level, freeze_level, spec_hash, updated_at)
sessions(id PK, symbol, session_name, start_ts, end_ts)
news_events(id PK, currency, importance, event_time, title)
parameter_sets(hash PK, json_blob, created_at)
runtime_events(id PK, ts, level, code, message)
system_health(id PK, ts, cpu_budget_used_ms, restart_marker, last_ontimer_ts)
```

Bulk writes always wrapped in `DatabaseTransactionBegin/Commit`. CSV export remains available
(`Storage/SignalLogger.mqh`) as a read-only projection of `signals` for Excel/Python — SQLite is
the source of truth per MetaQuotes' own guidance for `Files\` persistence.

## 4. Execution state machine (P0)

```
SIGNAL -> PREVIEWED -> USER_CONFIRMED -> REVALIDATING -> SUBMITTING
       -> ACCEPTED | REJECTED | UNKNOWN
       -> PARTIALLY_FILLED | FILLED
       -> POSITION_ACTIVE -> CLOSED -> OUTCOME_RECORDED
```

Rules:
- Every transition writes to `trade_requests`/`deals` inside a DB transaction — no in-memory-only state.
- `OnTradeTransaction` never assumes ordering (per MetaQuotes docs); every handler re-reads
  `PositionSelect`/`HistoryDealSelect` to confirm state rather than trusting event order.
- `UNKNOWN` is reconciled on the next `OnTimer` tick by cross-checking `HistoryDealsTotal()`.
- Restart recovery: on `OnInit`, any request left in a non-terminal state is re-reconciled
  against live positions/history before the EA resumes scanning.

## 5. Portfolio risk gates (P0)

Per-trade risk (existing) is extended with:
- Per-symbol open risk cap
- Total open risk cap
- Currency exposure (aggregate directional bet per currency, e.g. USD from EURUSD+GBPUSD+XAUUSD)
- Asset-class exposure cap
- Daily risk budget (resets on broker server day change)

A new trade is **BLOCKED** (not silently resized) when any cap is breached; the block reason is
shown in the Dashboard's Detail panel (explainability, see below).

## 6. News gate (P0, scoped down from the original proposal)

v1.2.0 ships only:
- `CalendarValueHistory` read of upcoming high/medium-impact events for the symbol's relevant
  currencies, using broker/server time.
- A `BLOCK_NEW_SIGNAL` gate inside a configurable pre/post-event window.

Deferred to **P2** (v1.3, not this pass): a static historical news dataset embedded as an MQL5
resource for realistic Strategy Tester backtesting. Building a reliable historical dataset is a
sub-project of its own and would slow down P0 execution-reliability work if pulled forward.

## 7. Multi-tab dashboard (P0)

Built as native MQL5 chart objects (`OBJ_RECTANGLE_LABEL` panel + `OBJ_BUTTON` tab strip +
`OBJ_LABEL`/`OBJ_EDIT` content), **not** `CCanvas` bitmap rendering — the EA's processing budget
is 20ms per timer slice, and object updates are cheaper than redrawing a bitmap every tick.
Tabs:

- **Overview** — one row per symbol: Regime (v1.3) / Bias / Setup / Long / Short / Spread / News / Status.
- **Detail** — click-through: H4/H1/M15/M5 state, S/R, Entry/SL/TP, Risk, explainability
  (score breakdown + block reasons), Probability placeholder (v1.3, marked "insufficient data"
  until Outcome Engine has samples — never a fabricated number).
- **Risk** — per-trade / open / currency / asset-class exposure, daily budget remaining.
- **News** — per-symbol next event, currency, importance, countdown.
- **Health** — restart marker, last tick age, CPU budget used, DB write failures, dedup counters.

## 8. Symbol/broker spec drift detection (P0 addition, not in the original proposal)

`Broker/SymbolSpec.mqh` gains a `ComputeSpecHash()` (digits, contract size, tick value,
stops level, freeze level). The hash is stored in `symbol_specs` and stamped onto every signal
(`broker_spec_hash`). On `OnInit`, if a symbol's live spec hash differs from the last stored one,
`SystemHealth` raises a warning — brokers changing contract specs mid-session is a real, silent
source of mispriced risk that the original proposal didn't call out.

## 9. What is explicitly NOT in v1.2.0

Matches the user's own cut list: no new indicators, no new setups, no Martingale/Grid, no
direct AI BUY/SELL, no ONNX, no DOM/Iceberg as core, no Telegram/external webhook in core, no
fabricated historical probability, no optimizer-driven parameter search. Native MT5 Push
Notifications only (`SendNotification`), not `WebRequest` (synchronous, unsupported in tester).

## 10. Licensing note

Architecture patterns referenced from EA31337 (GPL-3.0) are used as *ideas* (framework/strategy
separation, tester harness discipline) — no code is copied. PositionSizer (Apache-2.0) and
MQL5Unit (MIT) patterns for portfolio sizing and unit-test structure are safe to reference more
directly if literal snippets are ever pulled in; that should still be attributed if it happens.
