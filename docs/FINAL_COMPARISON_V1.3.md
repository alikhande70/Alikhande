# Alikhande Scanner — Final Engineering Comparison

Scope: source/design comparison only. Neither Claude nor GPT v1.3 receives runtime credit without MetaEditor/MT5 evidence.

| Area | GPT v1.2 baseline | Claude reviewed branch | GPT v1.3 independent rebuild |
|---|---:|---:|---:|
| Architecture separation | 8.5 | 9.4 | 9.6 |
| Structural/live signal correctness | 7.8 | 9.5 | 9.6 |
| Zone semantics | 7.5 | 9.6 | 9.7 |
| Explainable scoring | 8.2 | 9.5 | 9.6 |
| Signal lifecycle | 8.3 | 9.0 | 9.5 |
| SQLite persistence/migrations | 8.0 | 9.4 | 9.5 |
| Tester/optimization DB isolation | 7.0 | 7.0 reviewed | 9.3 design |
| Portfolio risk | 8.4 | 9.1 | 9.5 |
| Missing-SL fail-closed behavior | 6.5 | 7.5 reviewed | 9.7 |
| Demo-only / real hard block | 9.2 | 9.4 | 9.6 |
| OrderCheck preflight | 9.2 | 9.3 | 9.4 |
| OnTradeTransaction idempotency | 7.5 | 8.0 reviewed | 9.6 design |
| Restart reconciliation | 8.0 | 8.8 | 9.4 design |
| Calendar live/test separation | 8.0 | 7.5 reviewed | 9.5 |
| Professional multi-tab UI | 8.2 | 9.5 | 9.3 |
| Windows MT5 qualification design | 9.6 | 8.8 | 9.8 |
| Runtime evidence | 0 | 0 | 0 |

## Phase changes in GPT v1.3

| Phase | Main changes | Status |
|---|---|---|
| 0 | independent audit, architecture freeze, safety gates, project-director agent | PASS_STATIC |
| 1 | explicit runtime context; closed-bar structural snapshots separated from live quote state | PASS_STATIC |
| 2 | typed supply/demand zones; BELOW/INSIDE/ABOVE semantics; per-pass live validation | PASS_STATIC |
| 3 | explainable score components/penalties/vetoes; guarded lifecycle state machine | PASS_STATIC |
| 4 | runtime-isolated SQLite paths; transactional v4->v5 migration; feature/deal evidence tables | PASS_STATIC |
| 5 | deterministic portfolio risk; missing SL and failed risk calculation become blocking/unbounded | PASS_STATIC |
| 6 | persistent deal-ticket admission before memory mutation; authoritative history/position reconciliation | PASS_STATIC |
| 7 | explicit live/test calendar source; dedicated News tab; stronger UI explainability | PASS_STATIC |
| 8 | all v1.3 tests added to real MetaEditor compile gate | BLOCKED_RUNTIME |

## Overall engineering score

- GPT v1.2 baseline: **85/100**
- Claude reviewed source: **90/100**
- GPT v1.3 independent source/design candidate: **93/100**

The v1.3 score is intentionally capped below release-grade because no real MetaEditor compile, MT5 self-test execution, restart test or demo order evidence exists yet. A successful G8 qualification may justify reassessment; failure would reduce the score until corrected.

## Next blocking action

Run the Windows self-hosted MetaEditor gate on the v1.3 branch. Do not add new strategy features before compile/runtime errors, if any, are closed.
