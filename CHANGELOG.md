# Changelog

## v1.1.0 — ScannerPanel Hardening Edition

- Restored and hardened broker-aware symbol discovery.
- Added centralized assumption registry and documented ScannerPanel-derived defaults.
- Added symbol-spec warm-up, closed-bar caching, timer slicing, spread/ATR quality gates.
- Fixed EMA buffer chronology and available-information timing.
- Fixed neutral/directional score leakage.
- Added structural stops, 2R room-to-target validation, SignalID dedup, managed-chart reuse.
- Risk planner rejects below-minimum broker volume instead of silently increasing risk.
- Alert-only remains the safe default. Real-account execution remains blocked.
