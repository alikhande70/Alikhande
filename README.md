# Alikhande Scanner

MQL5 (MetaTrader 5) Expert Advisor — a multi-timeframe, zone-based trend scanner with an
alert-only dashboard. Real-account execution is not approved; demo execution is gated behind
explicit confirmation and risk checks.

## Status

This repository is being rebuilt on top of the `v1.1.0` release (source: Google Drive,
`alikhande_scanner_v1.1.0.zip`) into **v1.2.0 — Reliability & Evidence Edition**: a persistence,
execution-reliability, and portfolio-risk layer added around the existing scoring engines,
with zero new strategies/setups in this pass.

- Architecture blueprint: [`docs/ARCHITECTURE_V1.2.md`](docs/ARCHITECTURE_V1.2.md)
- Phased roadmap (v1.2 → v1.3 → v2.0): [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)

**Known gaps** (see `docs/ROADMAP.md` for full detail):

- The exact v1.1.0 binary source could not be transferred into this repo (chat-channel transfer
  unreliable at 37KB). The core engines (TrendEngine, ZoneEngine, SignalEngine, RiskPlanner,
  DemoExecution, SymbolResolver/Spec, etc.) were **rewritten from scratch** to match the
  documented v1.1.0 behavior in `docs/v1.1.0_README.md` / `docs/v1.1.0_ACCEPTANCE_TESTS.md`,
  not ported byte-for-byte.
- `AlikhandeScanner.mq5` wires the full scan → score → persist → dashboard pipeline, but the
  interactive Preview/Confirm-to-execute UI (buttons that drive a signal from CONFIRMED through
  PREVIEWED to an actual order) is not built yet — `Trading/DemoExecution.mqh` is complete and
  callable, just not yet triggered from the dashboard.
- **No MetaEditor/MT5 terminal is available in this build environment.** Nothing in this repo has
  been compiled or run. Every module should be treated as "believed correct, not proven to
  compile" until checked in a real MT5 environment (0 errors / 0 warnings is the required gate,
  per `docs/v1.1.0_ACCEPTANCE_TESTS.md`).

## Layout

```
MQL5/
  Experts/AlikhandeScanner/       EA entry point (pending v1.1.0 import)
  Scripts/AlikhandeScanner/       compile/test/discovery scripts
  Include/AlikhandeScanner/
    Core/                         config, hashing, version, new-bar detection
    Storage/                      SQLite persistence (NEW in v1.2.0)
    Domain/                       enums, models, signal lifecycle (NEW)
    Execution/                    order preflight, trade tracking, state machine (NEW)
    Risk/                         portfolio-level exposure gates (NEW)
    News/                         economic calendar gate (NEW)
    Health/                       restart recovery, telemetry, spec-drift detection (NEW)
    UI/                           multi-tab dashboard (NEW, replaces single-tab Dashboard.mqh)
    Tests/                        dependency-free unit tests (NEW)
    Analysis/ Broker/ Data/ Safety/ Signals/ Statistics/ Trading/
                                   existing engines (pending v1.1.0 import)
docs/                             architecture, roadmap, acceptance tests, technical spec
```
