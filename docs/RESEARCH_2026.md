# 2026 Research Decisions

## Adopted
- `OnTradeTransaction` event-driven reconciliation; event ordering cannot be assumed.
- Native SQLite for persistent signals/plans/executions/outcomes.
- `OrderCheck` as a preflight gate, with final state still reconciled after submission.
- Broker filling policy derived from symbol specification.
- Economic Calendar as a live high-impact gate; historical tester dataset is a separate validation phase.
- Walk-forward, parameter-stability and Monte-Carlo tools belong to validation, not the runtime scanner loop.
- Modular multi-symbol panel architecture.

## Rejected for v1.2
- ONNX/ML before a validated outcome dataset exists.
- DOM/iceberg as a core requirement for OTC FX/CFD feeds.
- More indicators or many new setup types.
- Web/Telegram dependencies in the trading core.
- Async order submission merely for novelty; this is not an HFT system.

## UI decision
Use object-based controls for tabs/actions and chart objects for price levels. Canvas remains optional for later dense visual analytics, not a mandatory runtime dependency.
