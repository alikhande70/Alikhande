# Phase 6 Evidence — Execution Reliability & Recovery

Status: **PASS_STATIC**

Implemented:
- `DealLedgerV13` provides persistent deal-ticket admission before any in-memory execution mutation
- duplicate deal replay is rejected by ticket across both current runtime and restart boundaries
- execution now requires an attached, ready SQLite database; otherwise sending is blocked
- intent persistence is required before `OrderSend`
- real-account hard block remains unconditional
- existing `OrderCheck` preflight remains mandatory
- `ReconcilerV13` rebuilds authoritative state from current positions plus MT5 deal history
- active position, fully closed history, entry-without-position and no-evidence outcomes are distinct states
- unknown/reconciling execution remains unresolved and therefore blocks a new send
- EA-level account-loss ingestion already filters deal magic before `RegisterClosedProfit`, preventing manual/other-EA deals from incrementing scanner consecutive losses
- self-test verifies persistent duplicate-ticket rejection

## Integration note

The new `AS_ExecutionEngine::Attach(repo,db)` overload is the required v1.3 attachment path. Existing legacy attachment is retained only for source compatibility and intentionally cannot execute because `SubmitDemo()` requires durable persistence.

MetaEditor, transaction ordering, partial-fill and restart runtime evidence remain pending Phase 8.
