# Alikhande Scanner v1.3 — Independent Phase Plan

This plan governs the independent GPT rebuild. Progression is gate-based, not feature-count based.

## Phase 0 — Baseline audit and architecture freeze

Deliverables:
- `AUDIT_GPT_BASELINE_V1.3.md`
- `ARCHITECTURE_V1.3.md`
- `SAFETY_GATES_V1.3.md`
- this phase plan

Exit: G0 PASS.

## Phase 1 — Deterministic runtime and market-data foundation

Build:
- runtime-context/environment model
- closed-bar structural snapshots
- explicit live quote state and freshness
- deterministic symbol scheduling/readiness
- indicator-handle lifecycle/registry where needed

Tests:
- same closed bars + different live quote does not alter structural identity
- stale/no-tick quote is explicit
- identical snapshots produce identical results regardless of scan slice order

Exit: G1 PASS by static/self-test evidence; Windows runtime remains pending G8.

## Phase 2 — Zone and signal semantics redesign

Build:
- typed zone relationship model
- structural candidates independent of live quotes
- live price validator
- current Entry/SL/TP preview and 2R feasibility

Tests include price below, on lower boundary, inside, on upper boundary and above zones.

Exit: G2 PASS.

## Phase 3 — Explainable score and lifecycle

Build:
- score component model
- penalties and hard-veto model
- structural candidate -> confirmed -> live tradable/blocked -> active -> terminal lifecycle
- evidence-aware historical probability read model

Exit: G3 PASS.

## Phase 4 — Persistence and evidence

Build:
- schema migration chain
- feature snapshots
- execution/deal uniqueness contract
- outcome storage
- runtime-context-aware database naming/isolation
- fail-closed persistence capability

Exit: G4 PASS.

## Phase 5 — Risk and portfolio engine

Build:
- deterministic position risk
- unbounded-risk policy for invalid/missing SL
- account/EA ownership policy
- currency/asset concentration and total risk caps
- restart-persistent account guard state

Exit: G5 PASS.

## Phase 6 — Execution reliability and recovery

Build:
- one demo-only send boundary
- OrderCheck preflight
- atomic intent persistence
- transaction deduplication before state mutation
- unordered OnTradeTransaction handling
- authoritative periodic/restart reconciler using history/orders/positions

Exit: G6 PASS.

## Phase 7 — Calendar and professional operator UI

Build:
- live/test calendar provider boundary
- explicit unavailable semantics
- Overview / Signal Detail / Risk / News / Health-Execution tabs
- explainability, freshness and block-reason rendering

Exit: G7 PASS.

## Phase 8 — Qualification and release evidence

Run on real Windows MT5 environment:
- all compile targets 0 errors / 0 warnings
- self-tests
- persistence/migration smoke
- duplicate-event replay
- restart recovery matrix
- Alert Only -> Shadow -> controlled Demo Confirm

Exit: G8 PASS. Only then may the build be labelled DEMO_QUALIFIED.

## Strategy-edge boundary

The engineering release does not assert profitability. Backtest, walk-forward and out-of-sample evidence are a separate statistical qualification track after correctness gates are established.
