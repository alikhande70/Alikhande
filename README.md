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

**Known gap:** the exact v1.1.0 `.mq5`/`.mqh` source (TrendEngine, ZoneEngine, SignalEngine,
RiskPlanner, DemoExecution, SymbolResolver, the original single-tab Dashboard, etc.) has not yet
been imported into this repo — see `docs/ARCHITECTURE_V1.2.md`. The new P0 modules under
`MQL5/Include/AlikhandeScanner/{Storage,Domain,Execution,Risk,News,Health,UI,Tests}` are
complete and self-contained, but the Expert Advisor entry point (`AlikhandeScanner.mq5`) that
wires them together still needs the original engines present to compile.

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
