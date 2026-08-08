# Acceptance Tests — v1.2 candidate

## Compile Gate
- CompileAllModules: 0 errors / 0 warnings.
- DatabaseSmoke: 0 errors / 0 warnings.
- SymbolDiscovery: 0 errors / 0 warnings.
- SymbolSpec: 0 errors / 0 warnings.
- AlikhandeScanner EA: 0 errors / 0 warnings.

## Broker Gate
- `EURUSD` resolves to broker symbol such as `EURUSD_o`.
- `XAUUSD` resolves where applicable.
- Unresolved symbols never generate signals.
- Broker specification drift is fingerprinted and logged.

## Runtime Gate
- Heavy analysis runs on newly closed bars, not every timer event.
- Persistent SignalID prevents duplicates after restart.
- Stale quotes block candidates.
- unresolved executions restore and reconcile after restart.

## Logic/Risk Gate
- H4 neutral gives neither direction a directional bonus.
- Setup requires zone proximity and M5 confirmation.
- SL is structural; nearer opposing zone blocks 2R.
- Lot below broker minimum rejects the plan.
- Actual monetary risk cannot exceed requested risk tolerance.
- Preview expiry and price drift block demo execution.
- Real accounts remain hard-blocked.
