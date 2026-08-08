# Alikhande Scanner v1.3 — Production Architecture

## Status of this document

This file describes the **actual v1.3 production source layout and enforced runtime flow** on branch `gpt/alikhande-scanner-v1.3-independent-rebuild-20260808`. Earlier drafts used conceptual directory names such as `Market/` and `Calendar/`; those names were architectural labels, not the filesystem. That ambiguity is removed here.

## Design principle

v1.3 separates four truths that must never be conflated:

1. **Structural market truth** — facts derived from closed bars and stable until the next structural refresh.
2. **Live quote truth** — bid/ask, spread, freshness and price-to-zone relationship evaluated on every scan pass.
3. **Authoritative execution truth** — current orders, positions, order/deal history and transaction events from MT5.
4. **Persisted evidence truth** — durable SQLite records used for recovery, audit and later statistical analysis.

## Actual source layout

```text
MQL5/Include/AlikhandeScanner
├── Core/
│   ├── Config.mqh
│   ├── Hash.mqh
│   ├── NewBarDetector.mqh
│   ├── RuntimeContext.mqh
│   └── VersionInfo.mqh
├── Data/
│   ├── MarketData.mqh
│   ├── RuntimeSnapshots.mqh
│   └── SpreadTracker.mqh
├── Analysis/
│   ├── TrendEngine.mqh
│   ├── ZoneEngine.mqh
│   └── RegimeEngine.mqh
├── Signal/
│   ├── SignalDomainV13.mqh
│   ├── ZoneSemanticsV13.mqh
│   ├── LiveValidatorV13.mqh
│   ├── ExplainableScoringV13.mqh
│   └── LifecycleV13.mqh
├── Signals/
│   ├── SignalEngine.mqh        # production facade using Signal/* modules
│   ├── SignalLifecycle.mqh     # production lifecycle facade
│   └── OutcomeEngine.mqh
├── Risk/
│   ├── PortfolioRisk.mqh
│   └── RiskMathV13.mqh
├── Trading/
│   └── RiskPlanner.mqh
├── Safety/
│   ├── AccountRiskGuard.mqh
│   └── TradeGuards.mqh
├── Execution/
│   ├── Preflight.mqh
│   ├── DealLedgerV13.mqh
│   ├── ReconcilerV13.mqh
│   └── ExecutionEngine.mqh
├── Persistence/
│   ├── DatabasePolicyV13.mqh
│   ├── Database.mqh
│   ├── Repositories.mqh
│   ├── ReadModels.mqh
│   └── RiskStateStore.mqh
├── News/
│   ├── CalendarProviderV13.mqh
│   └── NewsGate.mqh
├── Broker/
├── Health/
└── UI/
```

The temporary `V13` suffix marks modules introduced during this rebuild. It is not a second authoritative implementation: production facades explicitly call these modules, and the static gate rejects unreachable `.mqh` production modules. A naming cleanup may follow only after MetaEditor qualification, to avoid mixing refactoring with runtime verification.

## Production runtime flow

```text
Closed-bar change
  -> NewBarDetector
  -> TrendEngine closed-bar analysis
  -> typed supply/demand zones from ZoneEngine

Every scan pass
  -> MarketData -> RuntimeSnapshots -> fresh QuoteState
  -> RegimeEngine
  -> Signals/SignalEngine production facade
       -> ZoneSemanticsV13
       -> ExplainableScoringV13
       -> StructuralCandidateV13 stable identity
       -> LiveValidatorV13 current Entry / SL / TP / vetoes
  -> cached UI signal is refreshed even when signal_id is unchanged

Risk preview
  -> RiskPlanner
  -> PortfolioRisk -> RiskMathV13
  -> explicit Preview / DEMO confirmation

Execution
  -> real-account hard block
  -> Preflight -> OrderCheck
  -> persist intent
  -> single OrderSend boundary
  -> OnTradeTransaction
  -> DealLedgerV13 admission before fill-state mutation
  -> periodic/restart ReconcilerV13
       -> current Positions
       -> current Orders
       -> History Deals
       -> History Orders
```

## Non-negotiable invariants

- Real-account execution is impossible in v1.x by unconditional runtime hard block.
- `OrderSend` exists in exactly one production module.
- A deal ticket may mutate execution state at most once.
- Every sent intent is persisted before `OrderSend`.
- `UNKNOWN` execution outcome remains non-terminal and blocks new sends until authoritative evidence resolves it.
- Restart recovery uses SQLite plus current orders, current positions, history orders and history deals.
- Structural signal identity does not depend on live bid/ask.
- Entry/SL/TP are revalidated against the current quote on every scan pass before a signal is displayed as tradable.
- Price inside a valid demand/supply zone is a first-class interaction.
- Missing or unpriceable SL exposure is unbounded risk, never zero risk.
- Rule score is not a probability.
- Terminal/demo persistence is separated from tester/optimization persistence.
- News provenance is explicit: LIVE, TEST_DATA or UNAVAILABLE.
- UI renders domain state and issues commands; it does not contain hidden signal/execution logic.
- Static module reachability is necessary evidence, not a substitute for MetaEditor/MT5 runtime proof.

## Qualification boundary

Source/static gates may establish an implementation candidate. Only Windows MetaEditor/MT5 evidence can establish compile, shadow or demo qualification. No profitability claim follows from software correctness; backtest/OOS evidence is a separate statistical track.
