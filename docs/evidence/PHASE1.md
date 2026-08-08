# Phase 1 Evidence — Deterministic Runtime & Market Data

Status: **PASS_STATIC**

Implemented independently on the GPT v1.3 branch:

- `Core/RuntimeContext.mqh` explicitly distinguishes normal terminal, Strategy Tester and optimization execution contexts.
- `Data/RuntimeSnapshots.mqh` separates disposable live quote truth (`AS_QuoteState`) from closed-bar structural truth (`AS_ClosedBarSnapshot`).
- Structural snapshots reject `shift=0`, preventing accidental use of the forming candle.
- Structural identity is derived only from symbol, timeframe, closed-bar timestamp and OHLC values; bid/ask cannot alter it.
- `Phase1RuntimeSelfTests.mq5` checks runtime-context consistency, forming-bar rejection and deterministic closed-bar identity.

## Gate assessment

G1 design/static requirements are satisfied by source inspection. Actual MQL5 type checking and runtime self-test execution are **not proven** in this environment and are delegated to Phase 8 / G8.

No claim of MetaEditor compile success is made.
