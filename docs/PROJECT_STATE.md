# Project State

**Candidate:** v1.2.0-rc1  
**Branch intent:** reliability/evidence modernization  
**Runtime qualification:** not yet complete

## Completed in this candidate
- Drive v1.1.0 source recovered and used as real baseline.
- Persistent SQLite schema for signals, plans, executions, outcomes, broker specs and runtime events.
- Persistent signal deduplication.
- Execution state machine with `OnTradeTransaction` reconciliation and restart restoration.
- `OrderCheck` preflight and symbol-derived filling policy.
- Broker specification fingerprint/drift evidence.
- Deterministic regime context.
- Live high-impact economic-calendar gate.
- Portfolio scanner open-risk cap.
- Shadow signal outcome tracking.
- Multi-tab object-based dashboard and chart overlay.
- Static CI gate.

## Hard blockers before qualification
1. Real MetaEditor compile: 0 errors / 0 warnings.
2. LiteFinance demo symbol/spec/runtime validation.
3. Strategy Tester deterministic replay and no-look-ahead test.
4. SQLite restart/recovery runtime test.
5. Shadow sample collection and outcome audit.
6. Locked validation/OOS protocol.

## Current release verdict
**STATIC CANDIDATE — NOT YET DEMO-QUALIFIED.**
