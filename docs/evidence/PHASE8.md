# Phase 8 Evidence — Qualification

Status: **BLOCKED_RUNTIME**

Completed in source:
- Windows self-hosted MetaEditor workflow already exists.
- `tools/compile_mt5.ps1` now compiles the original smoke targets, all seven v1.3 phase self-tests, and the production EA.
- Gate remains strict: every compile target must report `0 errors, 0 warnings`.

Not yet established:
- no MetaEditor compile log for the v1.3 branch
- no execution of Phase1-Phase7 MQL5 self-tests
- no SQLite runtime/migration evidence
- no duplicate `OnTradeTransaction` replay evidence inside MT5
- no restart reconstruction matrix evidence
- no Alert Only / Shadow runtime smoke
- no controlled Demo Confirm execution evidence

Therefore v1.3 may be called a **DESIGN_CANDIDATE / STATIC IMPLEMENTATION CANDIDATE** only. It is not compile-qualified, shadow-qualified or demo-qualified until the Windows MT5 gate produces evidence.
