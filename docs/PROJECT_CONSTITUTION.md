# Alikhande Scanner — Project Constitution

## Immutable safety rules

1. Real-account execution is blocked in v1.x.
2. No martingale, grid, recovery, averaging-down, or loss-chasing logic.
3. Rule score must never be presented as win probability.
4. Historical probability is unavailable until outcome data and validation gates exist.
5. No look-ahead: signal decisions use information available at the decision timestamp.
6. Unknown execution/account/data state fails closed for execution.
7. Failed tests may not be removed or weakened merely to obtain a green build.
8. Locked OOS/forward data may not be re-used for tuning after inspection.
9. Every release claim must point to evidence.
10. `main` receives changes only through reviewed release candidates.

## Product objective
A multi-symbol MT5 scanner that is reliable, explainable, restart-safe and evidence-driven in Alert, Shadow and explicitly confirmed Demo modes.
