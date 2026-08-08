# Changelog

## 1.2.0-rc1
- Recovered v1.1.0 real source from Drive as implementation baseline.
- Replaced volatile CSV/registry authority with native SQLite persistence.
- Added signal lifecycle, outcomes, broker-spec fingerprints and execution evidence.
- Added `OrderCheck` preflight and event-driven execution reconciliation.
- Added restart recovery of unresolved executions.
- Added deterministic market regime, news gate and portfolio risk cap.
- Added Alert/Shadow/Demo-confirm run modes while preserving hard real-account block.
- Rebuilt dashboard as multi-tab object UI and added managed chart signal overlay.
- Removed active legacy `SignalRegistry`, `SignalLogger` and `DemoExecution` modules.
- Added repository static gate and agent/project governance documents.
