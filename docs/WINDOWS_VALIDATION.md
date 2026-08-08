# Windows / MetaTrader 5 Validation Gate

This gate is mandatory before v1.2 can be called compile-qualified or demo-qualified.

## Required environment
- Windows x64
- MetaTrader 5 + MetaEditor 64-bit
- LiteFinance demo terminal/account for broker validation
- GitHub self-hosted runner labels: `self-hosted`, `Windows`, `X64`, `mt5` (optional but recommended)

## Automated compile entrypoint
`tools/compile_mt5.ps1` stages the repository MQL5 tree into an MT5 data folder and compiles:

1. `CompileAllModules.mq5`
2. `DatabaseSmoke.mq5`
3. `PersistenceSmoke.mq5`
4. `SmokeDomain.mq5`
5. `SymbolDiscovery.mq5`
6. `SymbolSpec.mq5`
7. `AlikhandeScanner.mq5`

Every target must show **0 errors, 0 warnings** in a real MetaEditor log.

## Runtime qualification after compile
- Run `DatabaseSmoke` and `PersistenceSmoke` and retain logs.
- Validate LiteFinance symbol resolution and broker specifications.
- Start EA in **Alert Only** first.
- Verify all configured symbols reach synchronized data state.
- Restart MT5 and verify risk state / unresolved execution recovery.
- Run **Shadow** mode before any Demo Confirm test.
- Real-account execution remains prohibited in v1.x.

## Evidence rule
Static GitHub CI is not a substitute for MetaEditor. No release document may mark this gate PASS without the actual compiler/runtime logs.
