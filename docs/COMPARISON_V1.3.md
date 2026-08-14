# Three-way comparison — Claude v1.2 vs GPT v1.3 vs Claude v1.3

All GPT findings below are tool-verified, not impressions: the GPT branch was
checked out and analysed with this repository's own static gate.

## Headline

| | Claude v1.2 | GPT v1.3 | Claude v1.3 |
|---|---|---|---|
| Unreachable production modules | 0 | **8** | 0 |
| Uncached indicator handles | 0 | **5** | 0 |
| Uninitialised file-scope arrays | 0 | **3** | 0 |
| Structural/live split reaches production | yes | **no** (module is dead) | yes |
| Price-inside-zone usable | yes | **no** in production path | yes |
| Tester/optimization DB isolation | **no** | yes | yes |
| Deal replay cannot double-count | **no** | yes | yes |
| Stopless position blocks new risk | **no** | yes | yes |
| Calendar UNKNOWN ≠ CLEAR | **absent** | yes | yes |
| Order requires human confirmation | **no** (auto-sent) | yes | yes |
| Linter has its own tests | yes (35) | no | yes (41) |

## What GPT v1.3 got right, and I adopted

Four things in that branch are genuinely better than what I had, and studying it
exposed two outright bugs in my own code.

**1. Tester/optimization persistence isolation.** I had nothing. A backtest and
a live run wrote the same database, so any statistic computed later would have
been measuring a mixture — invisibly, because the rows look identical. Adopted
as an idea, implemented differently: GPT hashes the agent sandbox into a
filename for every context. I do that for a single backtest, but **disable
persistence outright during optimization**. A sweep runs thousands of passes
across parallel agents; a database per pass is by construction evidence about
nothing, since each pass is a different parameter set over the same history.
Per-pass results belong in `OnTester`/frames. Isolating the garbage is good;
not generating it is better.

**2. The deal ledger as an admission gate.** GPT's `DealLedgerV13` requires a
deal to pass the ledger *before* it may mutate execution state. Mine recorded
the ticket and then mutated `filled_volume` unconditionally, discarding
`RecordDealOnce`'s answer. Since MetaQuotes documents that transaction delivery
may repeat, my idempotency was decorative: a replayed `DEAL_ADD` double-counted
the fill and could drive a partially-filled order to FILLED on volume that
arrived once. **A real bug in my code, and the same class I had criticised in
the v1.1.0 audit.** Fixed, plus a static check (`DISCARDED_GUARD_RESULT`) so it
cannot come back.

**3. "Missing SL is not zero risk."** GPT's production `PortfolioRisk` sets
`scanner_unbounded_risk` and refuses. Mine returned `0.0` for a stopless
position — under a comment claiming such positions were "reported separately".
They were not. An unbounded position therefore read as *free* to every cap,
which is the most dangerous way a risk limit can fail: the more exposed the
account actually is, the more room the caps appear to have. **A second real bug
in my code, and the comment made it worse by looking handled.** Boundedness is
now an explicit output, unbounded positions are counted and named, and the gate
refuses before checking any cap.

**4. Calendar provenance and two-step confirmation.** LIVE / TEST_DATA /
UNAVAILABLE as distinct states, and requiring explicit human confirmation before
an order. Both adopted as ideas, both implemented independently — and I resolved
a question GPT's design leaves open (below).

I also adopted the **"four truths"** framing from their architecture document —
structural, live, authoritative-execution, persisted-evidence — as a way of
stating the layering rule. It is a good piece of thinking.

## What GPT v1.3 got wrong

**The v1.3 signal work is dead code.** This is the central problem. Eight
production modules are unreachable from the EA, verified by walking the include
graph:

```
Core/NewBarDetector.mqh          Signal/LiveValidatorV13.mqh
Data/RuntimeSnapshots.mqh        Signal/ExplainableScoringV13.mqh
Risk/RiskMathV13.mqh             Signal/LifecycleV13.mqh
Signal/SignalDomainV13.mqh       Signal/ZoneSemanticsV13.mqh
```

Each is referenced only by its own `PhaseNSelfTests.mq5`. The EA still includes
the old `Signals/SignalEngine.mqh`. So the branch's headline invariants are
documented, unit-tested, and **not in force**:

- *"Structural candidate identity does not change because bid/ask changes"* —
  the production `SignalEngine::Evaluate` still computes trend, zones, entry,
  stop and target in one call, gated on `c4||c1||c15||c5`, i.e. only on bar
  change. The stale-signal defect from v1.1.0 is still present in the running
  code. `LiveValidatorV13`, which would fix it, is never called.
- *"Zone INSIDE is a first-class relation"* — production `NearestZones` still
  requires `zones[i].high<=snap.bid`, so a zone containing price is still
  invisible. `ZoneSemanticsV13` is never called.

This is v1.1.0's B9 (four unreachable classes) reproduced at twice the scale,
and it is the failure mode `UNREACHABLE_MODULE` now guards against here.

**The architecture document describes a tree that does not exist.**
`ARCHITECTURE_V1.3.md` shows `Market/`, `Calendar/`, `Signal/ScoringEngine`,
`Tests/` as a source directory. The filesystem has `Data/`, `News/`,
`Signals/SignalEngine`, and tests under `Scripts/`. A design document that does
not match the code is worse than none, because it is trusted.

**`V13` filename suffixes are lasting debt.** `Signal/` and `Signals/` coexist,
as do `Risk/PortfolioRisk` and `Risk/RiskMathV13`, `Safety/` and `Risk/`,
`Trading/RiskPlanner` and the Risk layer. A reader cannot tell which is
authoritative. Version numbers belong in tags, not identifiers.

**v1.1.0 defects still present**, found by my gate on their tree: 5 uncached
indicator handles (`iMA`/`iATR`/`iADX` created per call), 3 uninitialised
file-scope arrays (the `g_last_alert` class of bug).

## Where I went further

**Optimization writes nothing at all** rather than writing isolated garbage.

**Calendar UNKNOWN resolves by context.** GPT states UNAVAILABLE must be
explicit but does not resolve what to *do* about it. Blocking on UNKNOWN
everywhere means no backtest ever trades, making the filter unfalsifiable rather
than safe; allowing it everywhere is fail-open. So: in production UNKNOWN
blocks — real orders against a calendar the system cannot see is precisely what
a news filter exists to prevent. In the tester it does not block, but the run is
flagged **NEWS-BLIND** and logged, because its results describe a system without
a news filter and are not comparable to a live run that has one.

**Arming is scoped to a specific plan.** Confirm refuses when the armed
`plan_id` no longer matches what is on screen, so a signal re-planned underneath
the operator cannot execute something they never evaluated; a refused confirm
disarms rather than lingering.

**The gate enforces the architecture.** `UNREACHABLE_MODULE` makes the
dead-module failure impossible to ship, and `DISCARDED_GUARD_RESULT` makes the
decorative-idempotency failure impossible to reintroduce. Both have positive and
negative self-tests. Validating the first also exposed a latent bug in the
analyser itself — mixed resolved/unresolved paths made every include lookup miss
and reported the whole tree as unreachable. A check that fails *open* like that
is worse than no check, because its output looks like a real finding.

## Kept, rejected, redesigned

**Kept from v1.1.0** (still correct, still in force): the symbol resolution
ladder; spread classification against the symbol's own median; the ATR quality
gate; `[ASSUMED]` vs `[POLICY]` tagging; structural stops with 2R and the
opposing-zone veto; rejecting sub-minimum lots rather than rounding up;
`has_historical_estimate` as an honesty flag; the sliced scheduler with a budget.

**Rejected from GPT v1.3**: the `V13` naming scheme; parallel `Signal/` and
`Signals/` trees; per-pass optimization databases; every line of its code — the
ideas were worth taking, the implementation was not mine to copy.

**Redesigned in this branch**: persistence policy (disable, don't isolate);
calendar unknown-resolution (context-dependent, not absolute); arming
(plan-scoped with TTL, not a global flag); zone relation (in Domain, not beside
the engine, because Models carries it and Domain must not depend upward).

**Fixed in my own code because of this study**: deal-replay double-counting;
unbounded-risk blindness. Both were properties I had *claimed* in comments and
not enforced — the exact failure I had criticised elsewhere.

## Not established

Nothing here has been compiled or executed: no MetaEditor or MT5 terminal exists
in this environment. Every module is statically verified and runtime unproven,
and the same is true of the GPT branch. No claim is made about either system's
profitability — there is no backtest, no out-of-sample result and no live record
for either. See `docs/VERIFICATION.md`.
