# Alikhande Scanner MT5

Evidence-driven multi-symbol scanner for MetaTrader 5. Current candidate: **v1.2.0-rc1**.

## Product modes
- **Alert Only** — analysis and alerts, no orders.
- **Shadow** — signals are tracked to outcomes without sending orders.
- **Demo Confirm** — a valid risk preview plus an explicit panel click is required; real accounts are hard-blocked.

## Architecture
The runtime separates broker/data, analysis, signals, persistence, risk, execution, health and UI. SQLite is the evidence store; CSV is no longer the authoritative state. `OnTradeTransaction` is the execution truth stream and the implementation does not assume transaction order.

## Safety/evidence posture
- No martingale/grid/recovery/averaging-down logic.
- Rule score is not a probability.
- Historical probability is disabled until sufficient validated outcomes exist.
- Unknown execution states fail closed.
- v1.x does not permit real-account execution.

## Local static gate
```bash
python tools/static_validate.py
```

## MT5 qualification
Copy `MQL5/Experts/AlikhandeScanner` and `MQL5/Include/AlikhandeScanner` into the terminal data folder, then compile the scripts in `MQL5/Scripts/AlikhandeScanner`. A release cannot be called compile-passed without a real MetaEditor log showing 0 errors / 0 warnings.

Read `docs/PROJECT_STATE.md`, `docs/ARCHITECTURE.md`, and `docs/ACCEPTANCE_GATES.md` before changing release status.
