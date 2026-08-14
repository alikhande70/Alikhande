# Architecture

## Pipeline

```
Broker/SymbolResolver      resolve requested name -> real broker symbol
Broker/SymbolSpec          read specification, fingerprint it, detect drift
        |
Data/MarketData            quote snapshot; a stale tick is a failure, not a value
Data/SpreadTracker         rolling median + percentile, per symbol
Data/IndicatorCache        one handle per (symbol, timeframe, kind, period)
        |
Analysis/TrendEngine       H4/H1/M15/M5 direction and strength   ] cached on
Analysis/ZoneEngine        typed supply/demand zones from pivots ] bar close
Analysis/RegimeEngine      trend / range / volatile / quiet      ]
        |
Signals/SignalEngine       LIVE: zone proximity, entry, stop, 2R target, score
Signals/SignalLifecycle    state machine, transitions persisted
        |
Risk/RiskPlanner           size against risk policy; reject below broker minimum
Risk/PortfolioRisk         aggregate, currency and asset-class exposure caps
Risk/AccountRiskGuard      daily loss, drawdown, consecutive losses (persisted)
Risk/TradeGuards           permissions, stops level, freeze level, exposure
        |
Execution/Preflight        revalidate, OrderCheck, broker filling policy
Execution/ExecutionEngine  the sole OrderSend boundary; reconciliation
        |
Persistence/Repositories   signals, features, plans, executions, deals, outcomes
Statistics                 Wilson interval over stored outcomes
UI/Dashboard               Overview / Detail / Risk / Health
```

## The structural/live split

The single most important design decision in this release.

`BuildContext()` runs only when a closed bar changed on one of the analysed
timeframes. It computes multi-timeframe trend, structural zones and regime —
things that genuinely cannot change between bar closes.

`Evaluate()` runs on **every** scan pass with the current quote. It recomputes
zone proximity, entry, stop, target, spread state and the score. It performs no
indicator reads and no history copies: it is arithmetic over cached structure,
which is what makes running it at 250 ms affordable.

v1.1.0 cached the *whole* candidate, including entry and the zone-proximity
decision, and displayed it against a live quote for up to five minutes. A
displayed signal must never be older than the tick beside it.

## Layer rules

- **Domain** holds data only. No behaviour.
- **Core** may not depend on anything above it.
- **Analysis** depends on Data, never on Risk or Execution.
- **Execution** is the only module that calls `OrderSend`. The static gate fails
  the build if a second call site appears.
- **UI** reads; it never mutates trading state.
- Everything that outlives a session goes through **Persistence**. No module
  keeps authoritative state in RAM only.

## Identity and versioning

Every persisted signal carries four stamps:

| Stamp | Meaning |
|---|---|
| `rule_version` | which setup-qualification logic produced it |
| `scoring_version` | which score weights produced it |
| `parameter_hash` | fingerprint of the tunables that shaped it |
| `broker_spec_hash` | the symbol specification in force at the time |

Outcome statistics are scoped by `rule_version`. Pooling results across a logic
change produces a win rate describing no system that ever ran.

`signal_id` is keyed on the *structural* situation — symbol, direction, setup,
confirming bar time, rule version — not on the live price. The same setup
re-evaluated seconds later at a slightly different quote is the same signal, so
it is stored once.

## Reconciliation model

MetaQuotes documents that trade transaction delivery is unordered, may repeat,
and may be dropped when the 1024-element queue overflows. Nothing here waits for
a particular event sequence:

- Intent is persisted **before** `OrderSend`, so a crash mid-flight is
  recoverable.
- Deals are recorded keyed by ticket, so a replayed event cannot double-count.
- Correlation uses request id, order ticket, deal ticket, or a magic-filtered
  symbol match — whichever arrives.
- A time-based sweep re-reads live position state and escalates anything still
  unresolved past the grace period, so a dropped event cannot wedge the engine.
- One execution is in flight at a time; concurrent sends cannot be attributed
  reliably under unordered delivery.

## Deliberate omissions

Not oversights:

- **No news gate.** MT5's calendar is unavailable in the Strategy Tester and
  holds no usable history, so a live-only gate would make backtests and live
  runs incomparable. Deferred until a static historical dataset exists.
- **No ONNX / machine learning.** The technical support exists in MT5. The
  dataset does not. `signal_features` is being captured now so the question
  becomes answerable later.
- **No depth of market.** Unreliable for OTC symbols and absent from the tester.
- **No Telegram or web hooks.** `WebRequest` is synchronous and unavailable in
  the tester; it would break reproducibility.
- **No new setups.** Adding strategies before the existing ones can be measured
  adds unfalsifiable claims, not capability.
