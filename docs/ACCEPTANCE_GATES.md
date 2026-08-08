# Acceptance Gates

| Gate | Requirement | Current |
|---|---|---|
| Source integrity | include graph + static policy checks | PASS locally |
| Compile | MetaEditor 0 errors / 0 warnings | NOT VERIFIED |
| Persistence | DB opens, schema migrates, restart recovery smoke | CODED / runtime pending |
| Safety | demo-only execution, fail-closed, no prohibited money management | STATIC PASS |
| Data | symbols/specs/history/ticks validated on LiteFinance demo | PENDING MT5 |
| Signal | no look-ahead + deterministic replay | PENDING TESTER |
| Statistics | no probability without evidence | PASS by design |
| Shadow | sufficient forward observations | PENDING |
| Demo | explicit confirmation + reconciliation | PENDING |
