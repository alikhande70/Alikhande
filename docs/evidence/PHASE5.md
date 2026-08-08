# Phase 5 Evidence — Risk & Portfolio

Status: **PASS_STATIC**

Implemented:
- scanner-owned positions are identified by magic before risk aggregation
- foreign/manual positions are explicit informational exposure and do not silently alter scanner loss accounting
- scanner positions with missing SL are treated as unbounded risk and block new risk instead of being skipped
- failed `OrderCalcProfit` is also fail-closed as unbounded risk
- deterministic risk aggregation helper and order-independence self-test
- total open-risk gate rejects invalid new-risk inputs and unbounded existing scanner exposure

Account-level closed-trade ownership is completed in Phase 6 at the transaction ingestion boundary.

MetaEditor/account-runtime proof remains pending Phase 8.
