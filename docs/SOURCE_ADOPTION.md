# ScannerPanel Source Adoption Record

## Directly grounded in available ScannerPanel files

- Full broker-tree symbol discovery.
- Assumption tagging and centralized configuration.
- Verified LiteFinance naming patterns: `_o`, `#`, and bare names.
- Spec warm-up concept.
- H4/H1/M15 hierarchy as broker-tested context; Alikhande keeps M5 confirmation.
- 250 ms timer, 20 ms budget and two-symbol slices as defaults.
- Spread and ATR regime gates.
- Alert-only safety default.
- Daily loss, total drawdown and consecutive-loss thresholds as disabled assumptions.

## Not copied because source files were unavailable

- ScannerPanel RiskManager implementation.
- ScannerPanel Executor implementation.
- ScannerPanel ScoreEngine and fitted model loading.
- ScannerPanel Gates, Structure, Levels and Features implementations.

Alikhande implementations with similar names are independent code and must pass their own compile and validation gates.
