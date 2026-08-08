# Changelog

## 1.3.0 — Evidence Integrity

Produced by studying an independent GPT rebuild, then acting on what it got
right. Two of the changes below fix real defects in v1.2.0 that the study
exposed. Full three-way analysis in `docs/COMPARISON_V1.3.md`.

### Fixed

- **Deal replay double-counted fills.** `OnTransaction` discarded
  `RecordDealOnce`'s answer and mutated `filled_volume` regardless. Since
  MetaQuotes documents that transaction delivery may repeat, the idempotency was
  decorative: a replayed `DEAL_ADD` could drive a partially-filled order to
  FILLED on volume that arrived once. The ledger is now an admission gate.
- **A stopless position read as zero risk.** `PositionRisk` returned `0.0` under
  a comment claiming such positions were "reported separately". They were not,
  so an unbounded position appeared *free* to every cap — the more exposed the
  account, the more room the caps seemed to have. Boundedness is now explicit
  and blocks before any cap is evaluated.

### Added

- **Runtime context and persistence isolation.** Terminal / tester /
  optimization are distinguished, and the database is routed per context so a
  backtest can never contaminate production outcome history. Optimization
  disables persistence outright rather than writing per-pass files.
- **Calendar gate with provenance.** LIVE / TEST_DATA / UNAVAILABLE are distinct
  states; UNKNOWN is never folded into CLEAR. Resolution is context-dependent:
  blocking in production, non-blocking but flagged NEWS-BLIND in the tester.
- **Two-step human confirmation.** `AS_MODE_DEMO_CONFIRM` replaces auto-execute.
  Arm and confirm are separate controls; the intent carries a TTL and refuses if
  the plan was superseded.
- **Zone relation as a first-class concept.** BELOW / INSIDE / ABOVE /
  UNAVAILABLE, wired into setup qualification and scoring — genuine interaction
  now scores above mere proximity.
- **Two static checks**, both from concrete defects: `DISCARDED_GUARD_RESULT`
  (an ignored idempotency guard) and `UNREACHABLE_MODULE` (production code
  nothing reaches from the EA). Gate self-tests now number 41.

### Changed

- Rule and scoring versions bumped to 1.3.0: setup qualification now requires a
  correctly-anchored zone and scoring gained a ZONE_INSIDE component, so stored
  outcomes from 1.2.0 describe different logic and must not be pooled.

### Not verified

Nothing has been compiled or executed — no MetaEditor or MT5 terminal exists in
this environment. No claim is made about profitability. See
`docs/VERIFICATION.md`.

## 1.2.0 — Reliability & Evidence

Rebuilt from the SHA-256-verified v1.1.0 baseline. No new setups: the release
adds the infrastructure needed to measure the existing ones.

### Fixed (see `docs/AUDIT_V1.1.0.md` for full detail)

- **B2** Signals were computed once per closed bar and then displayed, alerted
  and logged against a live quote for up to five minutes. Signal generation is
  now split: structure caches on bar close, everything price-dependent is
  recomputed every pass.
- **B5** The nearest-zone search required a zone to sit entirely on one side of
  the quote, so no setup could form while price was inside a zone — the exact
  moment the strategy targets.
- **B6** Swing highs and swing lows merged into one untyped zone sharing a touch
  counter, inflating the zone quality that feeds the score. Zones are now typed.
- **B8** Every closing deal on the account fed the risk guards, so manual trades
  and other EAs could halt the scanner. Now magic-filtered and de-duplicated by
  deal ticket.
- **B7** Restarting reset the peak-equity high-water mark, disarming the drawdown
  guard. Risk state is now persisted.
- **B4** Indicator handles were created and released per call. Now cached.
- **B1** `g_last_alert` was resized without initialisation, making the alert
  cooldown undefined on first use.
- **B3** A hard block cleared direction but left a phantom setup.
- **B10** The broker freeze level was read and never checked.
- **B11** A stale quote was reported as a successful snapshot.
- **B12** Dashboard columns were padded for a monospace font and rendered in a
  proportional one; buttons were pinned off-screen on narrow windows.

### Added

- SQLite persistence with versioned, stepwise migrations: signals, features,
  plans, executions, deals, outcomes, specifications, risk state, events.
- Signal lifecycle state machine with an explicit transition allow-list.
- Execution engine as the sole `OrderSend` boundary, with intent persisted
  before the send, idempotent fill accounting, restart recovery and a
  time-based reconciliation sweep that does not depend on event delivery.
- Shadow mode: full validation and persistence, no order sent.
- Portfolio exposure limits — aggregate, per-currency and per-asset-class.
- Broker specification fingerprinting with drift detection across restarts.
- Market regime classification (advisory).
- Wilson confidence intervals over stored outcomes, gated on a minimum sample.
- Four-tab dashboard with score-breakdown explainability.
- `tools/static_gate.py`: MQL5 static analyser with 13 checks and its own
  35-assertion test suite, running in CI.
- `RunSelfTests.mq5`: in-terminal tests for lifecycle, statistics, zone
  lookups, directional scoring, exposure and hashing.

### Removed

- `AS_SignalRegistry` (RAM-only de-duplication, superseded by the database).
- `AS_NewBarDetector`, `AS_DemoExecution`, the old `AS_RiskPlanner` and the
  caller-less `AS_Statistics` — all unreachable in v1.1.0.

### Policy

- Real accounts are refused unconditionally; `ENUM_AS_RUN_MODE` has no member
  that selects live trading.
- Martingale, grid, recovery and averaging down are rejected by the static gate.
- A rule score is never presented as a probability. Historical win rate appears
  only above the minimum sample threshold, always with its Wilson interval and
  sample size, and always scoped to one rule version.

### Not verified

Nothing in this release has been compiled or executed — no MetaEditor or MT5
terminal was available. See `docs/VERIFICATION.md`.

## 1.1.0 — ScannerPanel Hardening Edition

- Broker-aware symbol resolver and diagnostic scripts.
- Centralised assumption registry and sliced scheduler with processing budget.
- Quote staleness and symbol-spec warm-up.
- Fixed EMA CopyBuffer chronology; ATR-regime quality multiplier.
- Fixed H4-neutral short-score bug and bidirectional strength inflation.
- Structural zone-based stops, 2R room-to-target hard block.
- Unique signal logging registry; managed-chart reuse.
- Risk planner hardened against minimum-lot risk inflation.
- Optional account risk guard framework.

## 1.0.0

- Initial coded prototype foundation.
