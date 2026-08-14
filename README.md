# Alikhande Scanner

Two builds of one system:

| | |
|---|---|
| **[`desktop/`](desktop/) — Desktop 2.2.0** | A standalone Windows application. Its own process, window and database; MetaTrader runs headless in the background purely as a quote/execution gateway. Three declared environments, an in-app robot, connection supervision, crash recovery, backup/restore and diagnostics. 406 tests execute; the backtest runs; the outcome loop is closed. |
| **`MQL5/` — MT5 v1.3.0** | The MetaTrader Expert Advisor. Statically verified, never compiled. |

Read [`desktop/README.md`](desktop/README.md) first if you want the application,
and note its opening section on what "outside MetaTrader" can and cannot mean.

---

## Alikhande Scanner MT5 v1.3.0

**Edition:** Evidence Integrity
**Default mode:** Alert-only. Real accounts are blocked unconditionally.

A multi-timeframe, zone-based scanner for MetaTrader 5. It looks for pullback
and rejection setups at confirmed H1 structure, scores them against a fixed rule
set, sizes them under hard risk policy, and — in demo mode only — executes them
through a reconciled order pipeline.

## What this build is for

v1.1.0 could produce signals. It could not tell you whether they were any good,
because nothing survived a restart and no outcome was ever recorded. v1.2.0 is
the infrastructure that makes the question answerable: every signal, plan,
execution and outcome is persisted with the rule version and parameter
fingerprint that produced it.

No new setups were added in this release. That is deliberate — more strategies
before the existing ones can be measured is more unfalsifiable claims.

## Safety policy

These are structural, not configurable:

- **Real accounts are refused.** `ExecutionEngine::Submit` returns
  `REAL_ACCOUNT_BLOCKED` on any non-demo account. `ENUM_AS_RUN_MODE` has no
  member that selects live trading, so no input combination can reach it.
- **One OrderSend boundary.** `Execution/ExecutionEngine.mqh` is the only module
  permitted to send an order; the static gate fails the build if that changes.
- **No martingale, grid, recovery or averaging down.** The static gate rejects
  these patterns by name.
- **A rule score is not a probability.** The score is a weighted sum of
  conditions. Historical win rate appears only when at least
  `AS_MIN_OUTCOME_SAMPLE` real outcomes exist for that symbol, setup and rule
  version, and always alongside its Wilson interval and sample size.

## Run modes

| Mode | Plans | Preflight | Sends |
|---|---|---|---|
| `AS_MODE_ALERT_ONLY` (default) | no | no | no |
| `AS_MODE_SHADOW` | yes | yes | no |
| `AS_MODE_DEMO_CONFIRM` | yes | yes | demo only, after arm **and** confirm |

Shadow runs the identical validation and persistence path as demo and stops
short of the send, so it exercises the real code rather than a simulation of it.

No mode sends automatically. `DEMO_CONFIRM` requires two deliberate actions on
separate controls — arm, then confirm — and the armed intent expires after a
short TTL. An EA that fires on its own is not supervised, it is merely watched.

**Persistence is routed by runtime.** A live terminal writes production history;
a backtest writes an agent-scoped file clearly named as such; an optimization
sweep writes nothing. Records from different contexts can never mix, so a win
rate computed later is not silently measuring a parameter sweep.

## Layout

```
MQL5/
  Experts/AlikhandeScanner/     EA entry point
  Scripts/AlikhandeScanner/     compile harness, self-tests, broker diagnostics
  Include/AlikhandeScanner/
    Core/          config, versioning, hashing, de-duplicating logger
    Domain/        enums and plain-data models
    Broker/        symbol resolution, specification + drift detection
    Data/          indicator handle cache, quotes, spread statistics
    Analysis/      trend, structural zones, market regime
    Signals/       signal generation, lifecycle
    Risk/          sizing, portfolio exposure, account guards, trade guards
    Execution/     preflight, execution engine (sole OrderSend boundary)
    Persistence/   SQLite schema, migrations, repositories
    Statistics/    Wilson interval over stored outcomes
    UI/            multi-tab dashboard, theme
    Testing/       assertion harness
tools/                          static analysis gate and its tests
docs/                           architecture, audit, acceptance criteria
```

## Install

Copy `MQL5/` into the terminal's Data Folder, then compile in this order:

1. `Scripts/AlikhandeScanner/CompileAllModules.mq5` — parses every module,
   including ones the EA does not currently reference.
2. `Scripts/AlikhandeScanner/RunSelfTests.mq5` — run it; it must print PASSED.
3. `Scripts/AlikhandeScanner/SymbolDiscovery.mq5` — find your broker's exact
   symbol names.
4. `Scripts/AlikhandeScanner/SymbolSpec.mq5` — verify the specification numbers
   that position sizing depends on.
5. `Experts/AlikhandeScanner/AlikhandeScanner.mq5`

Required gate: **0 errors / 0 warnings** on all five.

## Development

```bash
python3 tools/test_static_gate.py   # the linter's own tests
python3 tools/static_gate.py        # the codebase gate
```

Both run in CI on every push. See `docs/VERIFICATION.md` for exactly what they
do and do not prove.

## Status

**A P0 was found in this build by running its Python port.** `find_nearest_zone`
does not require a zone to sit on one side of price — that was the v1.1.0 fix
which made the INSIDE case findable — so when price traded *below* a demand
zone, a LONG took `stop = zone.low - buffer`, which is **above** its entry.
`MathAbs(entry - stop)` hid the inversion from the distance check and every
downstream gate passed it. Fixed here as `STOP_ON_WRONG_SIDE_OF_ENTRY` plus
relation-aware zone anchoring. The static gate could never have caught it: the
code is well-formed and fully reachable. See `desktop/docs/VERIFICATION.md`.

**The outcome loop is not closed in this build.** It is closed in `desktop/`. Signals, plans, executions and deals are
persisted with full version provenance, but nothing writes the `outcomes` table
yet, so no win rate or probability is ever produced — `has_historical_estimate`
is permanently false and the UI correctly renders "n/a". See
`docs/VERIFICATION.md`. The infrastructure for evidence exists; the evidence
does not.

Not compiled. No MetaEditor or MT5 terminal exists in the environment this was
built in, so every module is *statically verified and unproven at runtime*.
`docs/VERIFICATION.md` is explicit about the gap. Compiling and running the self
tests on a real terminal is the next required step, and until it happens no
claim about this build should be treated as established.
