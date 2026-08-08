# Alikhande Scanner v1.3 — Independent GPT Baseline Audit

Branch: `gpt/alikhande-scanner-v1.3-independent-rebuild-20260808`

This audit is intentionally based on the GPT v1.2 reliability branch. No Claude source code is adopted. Lessons learned from external review are treated only as hypotheses to verify independently against this codebase.

## Audit objective

Establish the correctness and safety gaps that must be closed before v1.3 may be considered a compile-qualified or demo-qualified release candidate.

## Confirmed findings

### P0-01 — inside-zone blindness in signal selection

`AS_SignalEngine::NearestZones()` selects support only when `zone.high <= bid` and resistance only when `zone.low >= ask`. A price currently inside a valid zone therefore does not select that same zone as the nearest structural zone. This can suppress the intended pullback/rejection setup at the exact interaction point.

Owner: Signal / Zone architecture.

Required fix: replace scalar nearest-above/below logic with typed price-to-zone relationship semantics: BELOW, INSIDE, ABOVE. The live validator must accept INSIDE as direct structural interaction.

Acceptance: unit/self-test cases for below, boundary, inside, above, broken and invalid zones for both supply and demand.

### P0-02 — signal truth mixes structural and live state

`ScanOne()` refreshes trends only on newly closed bars but signal evaluation is triggered only when one of those structures changes. The candidate then embeds entry/SL/TP calculated from the quote at that evaluation time and can remain cached afterwards. Structural truth and executable/live truth are therefore represented by one object with one timestamp.

Owner: Runtime / Signal architecture.

Required fix: split immutable bar-close structural candidate from per-scan live validation and executable trade plan.

Acceptance: after a structural candidate is created, changing bid/ask without a new bar must update validity, entry, stop distance, 2R feasibility and block reasons without changing the structural candidate identity.

### P0-03 — execution duplicate events can double-count in memory

`AS_ExecutionEngine::OnTransaction()` adds `trans.volume` to `m_current.filled_volume` for every related DEAL_ADD event. There is no in-memory or persistent processed-deal gate on that transition. Replayed duplicate trade transactions can therefore inflate fill state.

Owner: Execution.

Required fix: a deal ticket must be accepted exactly once before any execution-state mutation. Persistent uniqueness and runtime state transition must share the same acceptance result.

Acceptance: replay the same deal event twice; recorded deal count, filled volume and execution state must be identical to processing it once.

### P0-04 — restart reconciliation is not authoritative reconstruction

Current recovery loads one unresolved execution, while `Reconcile()` mainly inspects current positions. It does not fully reconstruct state from order/deal history plus current orders and positions.

Owner: Execution / Persistence.

Required fix: restart reconciler must query authoritative terminal history and current account state, correlate by magic/symbol/tickets/position identifier and deterministically derive final execution state.

Acceptance: restart scenarios for pre-send persistence, accepted order, partial fill, fully filled active position, already closed position and unknown outcome.

### P0-05 — tester/optimization SQLite isolation is not proven

The baseline uses one configured SQLite filename. Parallel Strategy Tester optimization agents can therefore contend for or contaminate shared persistence unless path isolation is explicit.

Owner: Persistence.

Required fix: environment-aware database policy for terminal, tester single-run and optimization agent contexts. Optimization persistence must be isolated or intentionally ephemeral.

Acceptance: generated database identity differs deterministically by runtime context and optimization agent/test identity; production history can never be written by tester runs.

## P1 findings / redesign requirements

- Risk ownership must remain scoped to this EA's magic number and must define policy for manual positions when computing portfolio concentration.
- Position risk with missing/invalid SL must be treated as unbounded/blocking, never zero-risk.
- Signal score and historical probability are separate concepts and must remain visually and structurally distinct.
- Economic calendar needs provider separation: live terminal calendar versus explicit tester dataset/unavailable state.
- UI must be a projection of domain/read models, not a place where trading decisions are computed.
- All order sends must pass one non-bypassable execution boundary with real-account hard block and `OrderCheck` preflight.

## Audit conclusion

Baseline v1.2 contains a strong reliability skeleton but v1.3 requires a semantic redesign around four different truths: structural market state, live quote state, authoritative account/execution state and persisted evidence state. Mixing those truths is the principal source of hidden trading-system defects.
