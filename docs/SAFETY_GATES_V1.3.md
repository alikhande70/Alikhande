# Alikhande Scanner v1.3 — Safety Gates

A phase is not complete because code exists. It is complete only when its evidence gate passes.

## G0 — Source identity and architecture

PASS requires:
- v1.3 branch descends from GPT reliability baseline.
- no source adoption/cherry-pick from alternative implementation branches.
- architecture and audit documents present.
- every P0 has an owner module and acceptance test.

## G1 — Deterministic market runtime

PASS requires:
- structural computations consume closed bars only.
- quote freshness is explicit.
- live quote changes do not mutate structural candidate identity.
- every configured symbol has independent readiness state.
- scan slicing/order does not change analytical result for identical input snapshots.

## G2 — Signal and zone correctness

PASS requires:
- price-to-zone relationship supports BELOW / INSIDE / ABOVE.
- inside-zone interaction is covered by tests.
- broken/invalid/expired zones cannot generate a tradable candidate.
- Entry/SL/TP preview derives from current quote plus stable structural reference.
- opposing-zone-before-2R and structural-stop checks are live-revalidated.

## G3 — Explainable lifecycle

PASS requires:
- candidate, confirmation, live validation, blocked/tradable, activation, expiry, invalidation and outcome states are explicit.
- every score component and every hard veto is inspectable.
- score and historical probability are separate fields and UI concepts.
- no probability is shown below minimum evidence threshold.

## G4 — Persistence and tester isolation

PASS requires:
- versioned transactional SQLite migrations.
- durable signals, feature snapshots, plans, executions, unique deals, outcomes, risk state and broker spec history.
- terminal/demo database is isolated from Strategy Tester.
- optimization agents cannot share mutable production persistence.
- database failure trips a fail-closed capability state where persistence is required for safety.

## G5 — Risk and portfolio determinism

PASS requires:
- scanner-owned exposure is deterministically identified by magic and authoritative account state.
- manual/other-EA exposure policy is explicit rather than accidental.
- position without valid SL is unbounded/blocking risk.
- total open risk and concentration calculations are order-independent.
- daily loss/drawdown/consecutive-loss guards survive restart.

## G6 — Execution reliability

PASS requires:
- real account hard-block cannot be disabled by input/configuration.
- one production `OrderSend` call site.
- `OrderCheck` succeeds before any send.
- intent is persisted before send.
- duplicate deal tickets cannot mutate DB or in-memory execution twice.
- `OnTradeTransaction` does not assume event order.
- periodic reconciliation covers dropped events.
- restart recovery reconstructs from SQLite + history + current orders + positions.
- unknown outcome remains blocked from new sends until resolved.

## G7 — Calendar and UI

PASS requires:
- live calendar provider is never silently reused in tester semantics.
- tester uses explicit historical dataset provider or reports NEWS_UNAVAILABLE.
- dashboard includes Overview, Signal Detail, Risk, News and Health/Execution views.
- UI displays score breakdown, veto reasons, data source freshness and runtime safety state.
- UI cannot bypass execution/risk gates.

## G8 — Windows MT5 qualification

PASS requires actual evidence from Windows x64 MetaEditor/MT5:
- all production/test programs compile with 0 errors / 0 warnings.
- modular self-tests pass.
- SQLite smoke and migration tests pass.
- duplicate transaction replay test passes.
- restart reconstruction scenarios pass.
- alert-only and shadow runtime smoke pass on LiteFinance demo.
- demo-confirm path remains blocked on non-demo account.

Static analysis, Python checks or code review can support G8 but can never substitute for it.

## Release states

- DESIGN_CANDIDATE — architecture/code may be reviewed; no compile evidence.
- COMPILE_QUALIFIED — MetaEditor 0/0 and module tests pass.
- SHADOW_QUALIFIED — runtime + restart + reconciliation evidence passes without sending orders.
- DEMO_QUALIFIED — controlled demo execution tests pass.
- LIVE — intentionally unsupported in v1.x.
