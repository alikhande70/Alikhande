# Verification status — Desktop 2.2.0

Current source status: `STATIC_CANDIDATE`
Acceptance status: `BLOCKED` pending Windows + a real MetaTrader 5 terminal
Strategy status: `STRATEGY_EDGE_NOT_PROVEN`

The detailed final review for PR 6 is
[`E2E_FINAL_AUDIT_PR6.md`](E2E_FINAL_AUDIT_PR6.md). It is the authority for the
Worker boundary, exact broker attribution, Demo Fill → Outcome → Evidence
cycle, Shadow provenance, restart reconstruction and atomic backtest evidence.

## Executed locally

- The complete Python test suite passes under Linux, including the headless Qt
  subset.
- `tools/static_validate.py` combines the maintained MQL5 static gate with
  desktop compilation, sole-send-boundary, Worker ownership, exact
  reconciliation and atomic evidence checks.
- `tools/test_static_gate.py` exercises the MQL static analyser itself.
- The real MT5 adapter module executes against `tests/fake_mt5.py`, a double of
  the documented MetaTrader5 surface. This tests this repository's mapping and
  ownership logic, not MetaQuotes' real runtime behaviour.
- SQLite tests use real `sqlite3`: fresh schema v4, migrations, newer-schema
  refusal, deal idempotency, terminal-outcome crash recovery, transactional
  outcome/state/risk commits and rollback of a failed replay replacement.
- The UI is constructed and driven with Qt's offscreen platform. The live GUI
  receives only deep-copied snapshots and queued action results. Failed broker
  position/order reads render as unknown and halt arming rather than appearing
  as zero exposure.
- Reconnect rebuilds broker-derived symbol/spec metadata without rebuilding or
  losing execution state. Backtest cancellation is checked on every replay step
  and the UI refuses to destroy a still-running replay thread.
- Persisted signal identity includes parameter and broker-spec fingerprints;
  exact Deal identifiers are propagated into same-pass Position/Order reads,
  and duplicate/conflicting broker facts have adversarial coverage.
- Backtests run through the shared signal/risk/outcome pipeline. Synthetic bars
  prove mechanics only and are never market evidence.

The exact final test count and commit SHA belong in the PR handoff produced from
the final clean-tree run; they must not be copied from an earlier checkpoint.

## Not established here

The following are runtime gates, not source-review questions:

- real MetaTrader5 IPC and field semantics on Windows;
- controlled Demo fill, partial fill, close reason and restart behaviour;
- Python indicator parity with MT5 buffers;
- Windows packaging, high-DPI rendering and manual operator workflow;
- any out-of-sample strategy edge.

The fake terminal cannot close these gaps because it is built from the same
documentation as the adapter. A real Windows run must save the terminal,
compiler, database and screenshot evidence required by
[`docs/CODEX_ACCEPTANCE_CONTRACT.md`](../../docs/CODEX_ACCEPTANCE_CONTRACT.md).

## Required next sequence

1. Create a covered `calendar.csv` as documented in
   [`WINDOWS_INSTALL.md`](WINDOWS_INSTALL.md).
2. Run `python -m alikhande doctor`; require a Demo account and machine-gate
   success.
3. Run Alert-only and Shadow on the real terminal, saving logs and database
   rows.
4. Compare EMA/ATR/ADX output with MT5 on identical bars.
5. Only after those gates, run one controlled minimum-volume Demo Confirm and
   capture request → order → deal → position → close → outcome, including the
   prescribed restart case.

No real-account execution was performed. Nothing in this repository establishes
that the strategy is profitable.
