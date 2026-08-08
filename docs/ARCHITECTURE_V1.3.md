# Alikhande Scanner v1.3 — Architecture Freeze

## Design principle

v1.3 separates four truths that must never be conflated:

1. **Structural market truth** — facts derived from closed bars and immutable until the next structural refresh.
2. **Live quote truth** — bid/ask, spread, drift and price-to-zone relationship evaluated on every scan pass.
3. **Authoritative execution truth** — current orders, positions, trade history and transaction events from MT5.
4. **Persisted evidence truth** — durable SQLite records used for recovery, audit and future statistical analysis.

A module may consume another truth, but it must not silently rewrite its meaning.

## Target architecture

```text
AlikhandeScanner
├── Core
│   ├── Config
│   ├── RuntimeContext
│   ├── Scheduler
│   ├── NewBarDetector
│   └── Hash
├── Market
│   ├── MarketData
│   ├── QuoteState
│   ├── BarSnapshot
│   └── IndicatorRegistry
├── Analysis
│   ├── TrendEngine
│   ├── RegimeEngine
│   ├── ZoneEngine
│   └── StructureEngine
├── Signal
│   ├── StructuralCandidate
│   ├── LiveValidator
│   ├── ScoringEngine
│   ├── SignalLifecycle
│   └── Explanation
├── Risk
│   ├── PositionRisk
│   ├── PortfolioExposure
│   ├── AccountRiskGuard
│   └── RiskBudget
├── Execution
│   ├── TradePlan
│   ├── Preflight
│   ├── ExecutionEngine
│   ├── TransactionDeduplicator
│   └── Reconciler
├── Persistence
│   ├── Database
│   ├── Migrations
│   ├── SignalRepository
│   ├── ExecutionRepository
│   └── OutcomeRepository
├── Calendar
│   ├── LiveCalendarProvider
│   ├── TesterCalendarProvider
│   └── NewsGate
├── UI
│   ├── Overview
│   ├── SignalDetail
│   ├── Risk
│   ├── News
│   └── Health
└── Tests
    ├── Domain
    ├── Signal
    ├── Risk
    ├── Execution
    ├── Persistence
    └── Restart
```

## Runtime data flow

```text
Closed-bar refresh
  -> BarSnapshot
  -> Trend/Regime/Structure/Zone analysis
  -> StructuralCandidate (stable identity)

Every scan pass
  -> QuoteState
  -> price-to-zone relationship
  -> LiveValidator
  -> Explainable score/veto set
  -> TradePlan preview

Explicit demo confirmation only
  -> Risk gates
  -> OrderCheck preflight
  -> single ExecutionEngine boundary
  -> OrderSend
  -> OnTradeTransaction
  -> idempotent state transition
  -> periodic/restart reconciliation
  -> outcome lifecycle
```

## Non-negotiable invariants

- Real-account execution is impossible in v1.x by unconditional runtime hard block.
- `OrderSend` exists in exactly one production module.
- A deal ticket mutates execution state at most once.
- Every sent intent is persisted before `OrderSend`.
- Restart recovery derives state from SQLite plus MT5 history/orders/positions; SQLite alone is not authoritative.
- Structural candidate identity does not change because bid/ask changes.
- Entry/SL/TP preview must be recalculated or explicitly invalidated from current live conditions.
- Missing SL is not zero risk.
- Rule score is not a probability.
- Tester/optimization persistence cannot contaminate terminal/demo history.
- News state must explicitly identify LIVE, TEST_DATA or UNAVAILABLE source.
- UI is read-only with respect to analytical truth; interactions issue commands but do not calculate hidden trading logic.

## Execution modes

- **ALERT_ONLY** — analysis and display only, no executable intent.
- **SHADOW** — complete live validation, risk and preflight path but no order leaves MT5.
- **DEMO_CONFIRM** — explicit user confirmation required before execution; demo account only.

No live mode exists in v1.x.

## Versioning discipline

Rule logic, scoring logic, database schema, parameter set and broker specification each carry independent version/hash identity. Historical outcomes are meaningful only when those identities are retained with the signal.
