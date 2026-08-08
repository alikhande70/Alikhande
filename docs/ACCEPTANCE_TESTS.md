# Acceptance Tests — v1.1.0

## Compile Gate

- CompileAllModules: 0 errors / 0 warnings.
- SymbolDiscovery: 0 errors / 0 warnings.
- SymbolSpec: 0 errors / 0 warnings.
- AlikhandeScanner EA: 0 errors / 0 warnings.

## Broker Gate

- `EURUSD` resolves to the broker's real symbol, e.g. `EURUSD_o`.
- `XAUUSD` resolves to `XAUUSD_o` where applicable.
- Unresolved symbols show `UNRESOLVED` and never generate signals.
- Symbol specs become ready without blocking OnInit indefinitely.

## Runtime Gate

- Bid/Ask/Spread refresh without repeating heavy analysis every timer event.
- H4/H1/M15/M5 analysis changes only on a newly closed bar for that timeframe.
- Repeated timers cannot append the same SignalID twice.
- Repeated Open clicks reuse an Alikhande-managed chart when configured.
- A stale quote blocks candidates.

## Logic Gate

- H4 neutral gives neither direction a directional bonus.
- H1 strength benefits only its own direction.
- No setup label is emitted without zone proximity and M5 confirmation.
- SL is outside the relevant H1 zone with ATR protection.
- TP equals 2R and a nearer opposing zone blocks the candidate.
- Pivot ConfirmationTime is the close time of the confirming bar.

## Risk Gate

- Raw lot below broker minimum rejects the plan.
- Normalized lot cannot exceed requested monetary risk by more than 1% rounding tolerance.
- Preview expiry and price drift block demo execution.
- Alert-only mode blocks order sending.
- Real accounts remain blocked.
