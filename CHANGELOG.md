# Changelog

## Desktop 2.1.0 — The Scanner screen

The application now opens on an answer rather than a dashboard. Ranked
opportunities on the left, the chart and the reasoning beside them, and a
percentage against each symbol — with the discipline that makes a percentage
safe to show.

### Added

- **An evidence layer with three tiers** (`core/evidence.py`). A displayed
  number is `MEASURED` (≥30 resolved trades — a real rate, with its 95%
  interval), `PROVISIONAL` (8–29 — the interval only, headline withheld), or
  `UNMEASURED` (the rule score, in grey, labelled *not a probability*). The
  request was "show me the percentage"; the constraint has been "a rule score
  is not a probability" since v1.1.0. Both are satisfiable, but only by saying
  out loud which one is on screen.

- **Expectancy in R as the ranking key, not win rate.** 70% at 0.5R loses
  money; 40% at 3R makes money. Rows sort on `p · RR − (1 − p)` computed from
  the **Wilson lower bound**, so a 60% rate over n=200 outranks 65% over n=31 —
  ranking on the point estimate systematically promotes the smallest sample.
  The break-even rate `1 / (1 + RR)` is shown beside RR, because "needs 29%,
  measuring 62%" is checkable and "62%" is not.

- **Provenance on every rate.** Outcomes carry the run kind they came from and
  the row says *from backtest* / *from live-demo* / *mixed*. A win rate whose
  source is hidden is how a backtest ends up quoted as live performance.

- **`alikhande calibrate`.** Seeds the evidence base by replaying history into
  the database the application reads, under a `REPLAY` run. Solves a real
  chicken-and-egg problem: the 30-sample floor is correct, and it means a fresh
  install shows NO DATA everywhere for weeks. Re-running *replaces* the previous
  calibration — appending would double the sample behind every rate while
  describing the same trades twice.

- **Presets: Default, Auto, Manual** (`profiles.py`). Auto tightens where the
  measured record justifies it and **has no mechanism for loosening** — an
  adaptive system that can relax its own thresholds will relax them all the way
  down after a good run. All three clamp to the same policy floors, enforced
  where the config is built, so a hand-edited preferences file does not get past
  them either.

- **`ScanEngine.reconfigure`** applies a preset between passes, through the same
  worker queue as every other operator intent. Refused outright while an
  execution is unresolved or an intent is armed: rebuilding the execution engine
  mid-flight would orphan a real order while the application forgot it existed.

- **`tools/render_ui.py`** renders every view, in both themes and both
  languages, offscreen. A design decision that survives a commit message and
  dies on contact with a screenshot is one nobody checked.

### Changed

- **The theme is monochrome, in light and dark.** Surfaces, borders, text and
  chrome are pure neutrals; the primary action is the inverse of the plane
  (white on near-black, black on white). This is functional rather than
  tasteful: the few coloured things left are the only things carrying meaning.
  Candles are neutral too — an up bar is terrain, not a signal, and tinting
  several hundred of them drowns out the zone, entry, stop and target. The rule
  score's ramp went from saturated blue to grey, because a calibrated-looking
  ramp makes a rule score look like a probability.
- `PALETTE` is now a proxy onto the active palette, so a theme switch takes
  effect without a restart and without touching the ~100 `PALETTE.x` reads in
  the widget layer.
- The nav badge moved from Signal to Scanner, and counts only setups **backed
  by evidence** — inflating it with unmeasured ones is how a badge becomes
  background noise.
- The backtester now registers its run in the `runs` table. Without that row
  every outcome it wrote reported unknown provenance.
- The in-app Guide gained four sections, EN and FA: reading the percentage,
  why EDGE matters more than win rate, where the numbers come from, and how the
  presets clamp.

### Not claimed

Nothing here has been run on Windows or against a live terminal — this was
built and tested on Linux, and PyInstaller does not cross-compile. The
calibration ships synthetic bars: it proves the machinery end to end and says
nothing whatever about this strategy's edge on real prices.

## Desktop 2.0.0 — Standalone

The scanner as a Windows application running outside MetaTrader: its own
process, window, database and logic, with the terminal reduced to a headless
quote-and-execution gateway. MetaQuotes publishes no other supported path for an
external program to reach an MT5 account — `desktop/README.md` opens with what
that does and does not make possible.

### Fixed — a P0 in the strategy, present in the MQL5 build too

- **An inverted stop could pass every gate.** `find_nearest_zone` deliberately
  does not require a zone to sit on one side of price; that was the v1.1.0 fix
  which made the INSIDE case findable at all. The cost was that a demand zone
  price had fallen *below* was still "nearest", so a LONG took
  `stop = zone.low - buffer` — **above** its entry — and `abs(entry - stop)` hid
  the inversion from the distance check. The result is a position whose stop and
  target sit in the same direction.

  Found by running the backtest and noticing its arithmetic was impossible:
  1,197 wins and 8,444 losses at 2R cannot total +8,130 R. 76 trades labelled
  `SL` had returned +1.0 R. Fixed in both builds as
  `STOP_ON_WRONG_SIDE_OF_ENTRY`, plus relation-aware zone anchoring so a broken
  zone cannot anchor a trade at all. The static gate could not have found it —
  the code is well-formed, reachable and type-correct.

### Added

- **A pure core with no external imports.** Analysis, risk, execution and
  statistics import no MetaTrader, no Qt and no sqlite. This is what makes the
  whole pipeline executable and testable anywhere, which the MQL5 build never
  was. CI installs no dependencies for the desktop job specifically to keep it
  that way.
- **The outcome loop, closed.** `core/outcomes.py` tracks an ACTIVE signal to
  its TP or SL and records realised R, MFE and MAE. In the MQL5 build
  `SaveOutcome` was defined and called by nothing, so `has_historical_estimate`
  was permanently false and every probability rendered "n/a" forever. A backtest
  run now writes 1,247 outcomes that the statistics layer reads back and turns
  into a Wilson interval.
- **A backtest engine that shares the strategy rather than reimplementing it.**
  It advances a cursor on an offline gateway and calls the same `SignalEngine`,
  `RiskPlanner` and `OutcomeTracker` the live app uses. Look-ahead is prevented
  structurally: the cursor truncates every series and higher timeframes advance
  proportionally, so H1 cannot leak a bar past M5. Every report states its own
  limits, including that a bar spanning both stop and target is scored a stop.
- **180 executed tests**, covering every safety gate — including a mechanical
  assertion that `send_order` appears nowhere outside the execution boundary.
- **A third independent real-account refusal.** The MT5 adapter refuses in
  `send_order` through code sharing nothing with the engine's check.
- **Indicators computed in-process**, removing MetaTrader's handle exhaustion,
  `BarsCalculated` timing hazards, and the untestability of both.
- **A five-tab PySide6 desktop UI** — Overview, Signal Detail, Risk, Execution,
  Health — with Arm and Confirm as separate controls and a live TTL countdown.
  All broker access is confined to one worker thread.
- **PyInstaller packaging** that refuses to build from a failing test suite.

### Known gaps

Live broker access has never executed, indicator agreement with MetaTrader is
derived from documentation rather than measured, and no out-of-sample result on
real data exists. `desktop/docs/VERIFICATION.md` is explicit about all three.

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
