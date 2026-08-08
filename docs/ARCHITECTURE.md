# Architecture — v1.2 Reliability & Evidence

```text
Broker/Data -> Data Quality -> Regime/News Context -> MTF Analysis/Zones
            -> Signal Engine -> Signal Lifecycle -> SQLite Evidence
            -> Risk/Exposure -> Preflight -> Demo Execution
            -> OnTradeTransaction -> Reconciliation -> Outcomes/Statistics
            -> Multi-tab Dashboard + Chart Overlay
```

## Boundaries
- **Domain**: enums and plain data models.
- **Broker**: symbol resolution, specifications and specification drift.
- **Data**: synchronization, snapshots and spread regimes.
- **Analysis**: trend, zones and deterministic market-regime context.
- **Signals**: rule scoring, lifecycle and outcomes.
- **Persistence**: native MQL5 SQLite schema and repositories.
- **Risk**: per-trade and portfolio scanner exposure.
- **Execution**: preflight, submit, event-driven reconciliation.
- **Health**: capability matrix and fail-closed circuit breaker.
- **UI**: lightweight object controls; chart overlays remain independent.

## Explicitly deferred
ONNX, direct AI buy/sell, DOM/iceberg, Telegram/WebRequest core dependencies, correlation optimizer and strategy proliferation.
