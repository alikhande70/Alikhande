# Roadmap

## Phase 0 — Baseline recovery — PASS (source recovered)
- Recover v1.1.0 from Drive.
- Preserve source provenance.
- Identify missing reliability layers.

## Phase 1 — Reliability core — IMPLEMENTED, COMPILE NOT VERIFIED
- SQLite schema and repositories.
- Persistent signal deduplication.
- Execution state model and restart restoration.
- OnTradeTransaction reconciliation.
- Broker-spec hash and preflight.
- Circuit breaker/capability matrix.

## Phase 2 — Market context — IMPLEMENTED CANDIDATE
- Deterministic regime engine.
- Live high-impact news gate.
- Spread state and data readiness.
- Portfolio scanner open-risk guard.

## Phase 3 — Professional panel — IMPLEMENTED CANDIDATE
- Multi-tab shell.
- Overview, signal, risk and system screens.
- Managed chart reuse and signal overlay.

## Phase 4 — Evidence pipeline — PARTIAL
- Shadow lifecycle and outcomes.
- Wilson/Brier/expectancy primitives.
- Remaining: MFE/MAE path tracking, historical probability query layer.

## Phase 5 — Validation tooling — PLANNED
- Windows MetaEditor compile gate.
- Real-tick strategy tests.
- locked IS/validation/OOS protocol.
- Walk-forward, spread/slippage stress, parameter stability, Monte Carlo.

## Phase 6 — Demo qualification — BLOCKED UNTIL PHASE 5
- Explicit confirmation only.
- No real-account release in v1.x.
