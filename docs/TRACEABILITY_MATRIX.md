# Traceability Matrix

| Requirement | Implementation | Evidence now | Gate |
|---|---|---|---|
| Multi-symbol scan | `AlikhandeScanner.mq5` | source/static | compile/runtime pending |
| MTF H4/H1/M15/M5 | Trend engine + orchestrator | source/static | tester pending |
| Support/resistance | `ZoneEngine.mqh` | source/static | tester pending |
| Market regime | `RegimeEngine.mqh` | source/static | calibration pending |
| Spread gate | `SpreadTracker.mqh` | source/static | broker runtime pending |
| News gate | `NewsGate.mqh` | source/static | live/tester split pending |
| Persistent signal IDs | SQLite repository | static gate | runtime restart pending |
| Trade-plan risk | `RiskPlanner.mqh` | static boundary | broker runtime pending |
| Portfolio risk | `PortfolioRisk.mqh` | static boundary | runtime pending |
| Real-account hard block | `Preflight.mqh` | static PASS | runtime negative test pending |
| Order preflight | `OrderCheck` | static PASS | demo runtime pending |
| Event reconciliation | `ExecutionEngine.mqh` | static PASS | partial/reject tests pending |
| Restart recovery | DB unresolved execution restore | static PASS | restart test pending |
| Historical probability honesty | unavailable by default | static PASS | evidence pipeline pending |
| Multi-tab dashboard | `Dashboard.mqh` | static/source | MT5 visual test pending |
| Chart levels | `ChartOverlay.mqh` | source | visual test pending |
