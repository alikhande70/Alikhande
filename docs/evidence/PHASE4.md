# Phase 4 Evidence — Persistence & Runtime Isolation

Status: **PASS_STATIC**

Implemented:
- explicit database-file policy for terminal, tester and optimization contexts
- production terminal history never shares the tester/optimization filename
- optimization/test identities include the actual terminal data-path hash
- database schema identity advanced to v5
- legacy v4 shape is bootstrapped without destructive replacement
- migration v4 -> v5 runs transactionally
- v5 adds `signal_features`, unique `execution_deals`, runtime identity and indexes
- database refuses unsupported newer schema
- self-test covers path isolation and runtime database open/migration

MetaEditor/SQLite runtime semantics remain pending Phase 8.
