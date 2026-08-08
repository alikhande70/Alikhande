# Verification status

Being precise about what has and has not been established matters more here than
anywhere else in the project: this is a system whose entire purpose is to stop
people trusting unverified claims.

## What has been verified

### Baseline provenance — VERIFIED
All 31 files of `baseline/v1.1.0-verified-drive` were checked against
`MANIFEST.sha256` before any work began: 31 OK, 0 FAILED. The rebuild starts from
authenticated source, not from a reconstruction.

### Static properties — VERIFIED by `tools/static_gate.py`
Runs in CI on every push. Currently passing across 33 files / 5400 lines:

- Include graph resolves; no cycles.
- Brackets balance, comment- and string-aware.
- Every `AS_*` identifier resolves to a `#define`, enum member, type or function.
- Struct member accesses exist on the accessed type (catches `plan.enrty`).
- No free function is called above its definition (a hard MQL5 compile error).
- No `Copy*` return value is discarded.
- No indicator handle is created outside the cache.
- No file-scope array is resized without initialisation.
- `OrderSend` appears in exactly one module.
- Forbidden patterns (martingale, averaging down, `OrderSendAsync`, `WebRequest`)
  are absent.
- Required safety invariants (`REAL_ACCOUNT_BLOCKED`, demo guard,
  `OnTradeTransaction`, probability honesty flag) are present.

The gate has its own test suite — `tools/test_static_gate.py`, 35 assertions,
each check tested both for firing correctly and for staying silent on correct
code. It was validated against the v1.1.0 baseline, where it independently
rediscovered B1 and B4 from the manual audit.

### Numeric expectations — VERIFIED
The Wilson interval bounds asserted in `RunSelfTests.mq5` were computed
independently before being written into the tests.

## What has NOT been verified

### Compilation — NOT VERIFIED
**No MetaEditor or MT5 terminal exists in the environment this was built in.**
Nothing here has been compiled. The static gate catches a real and useful class
of compile errors — it caught a genuine forward-reference bug in the EA during
this build — but it is not a compiler and does not attempt to be one. Type
checking, overload resolution, const-correctness and MQL5-specific semantics are
entirely unchecked.

Every module should be treated as **statically verified, runtime unproven**.

### Runtime behaviour — NOT VERIFIED
No module has executed. Specifically unproven:

- SQLite schema creation and migration against a real MT5 SQLite build.
- Indicator cache behaviour under real `BarsCalculated` timing.
- Zone detection against real price series.
- `OrderCalcProfit` / `OrderCalcMargin` results on a real broker.
- Preflight against real `OrderCheck` retcodes and filling modes.
- Transaction reconciliation against real, genuinely out-of-order delivery.
- Dashboard layout and rendering on a real chart.

### Strategy edge — NOT VERIFIED, AND NOT CLAIMED
There is no backtest, no walk-forward, no out-of-sample result and no live
record. The rule score is a weighted sum of conditions the author believes
matter. **Nothing in this repository constitutes evidence that the strategy is
profitable.** The persistence layer exists precisely so that this can eventually
be answered with data instead of opinion.

## Known open gap — the outcome loop is not closed

`Repositories::SaveOutcome` is defined and **called by nothing**. The `outcomes`
table is therefore never populated, `OutcomeCounts` always returns zero,
`has_historical_estimate` is permanently false, and `AS_FormatProbability`
always renders "n/a".

Everything downstream of that is correct and inert: the Wilson interval, the
minimum-sample gate, the rule-version scoping. The signal lifecycle reaches
`AS_SIGNAL_ACTIVE` and stops — nothing drives it to TP or SL, so nothing is ever
scored.

This is the same class of defect as v1.1.0's B9, where a correct Wilson
implementation was never called. v1.2/v1.3 wired the caller; the data it needs is
still not written.

**Consequence for how this build should be described:** it captures signals,
plans, executions, deals and features with full version provenance. It does not
yet produce outcome statistics of any kind. The infrastructure for evidence
exists; the evidence does not. Closing this loop — tracking an ACTIVE signal to
its TP/SL and writing the realised R, MFE and MAE — is the single highest-value
remaining piece of work, and no claim about win rate is possible before it.

## Required next steps

1. Compile all five programs in MetaEditor. Gate: 0 errors / 0 warnings.
2. Run `RunSelfTests.mq5`. Gate: PASSED.
3. Run `SymbolDiscovery.mq5` and `SymbolSpec.mq5` against the target broker;
   confirm every `[ASSUMED]` value in `Config.mqh` that the specification report
   touches.
4. Run alert-only on demo for a period long enough to accumulate signals, and
   confirm the database fills correctly and survives a deliberate restart.
5. Only then consider shadow mode, and only after that, demo execution.

Steps 1–2 are blocking. Until they pass, this build is a design that has not yet
been shown to run.
