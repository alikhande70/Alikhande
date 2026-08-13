# Alikhande Scanner Desktop 2.0.0

A standalone Windows application. Its own process, its own window, its own
database. MetaTrader is not part of its interface.

## What "outside MetaTrader" actually means

This matters more than anything else on this page, so it goes first.

MetaQuotes publishes **exactly one** supported way for an external program to
reach an MT5 account: the [`MetaTrader5` Python package][mt5pkg], which talks to
a **running, logged-in terminal** over local IPC. There is no MT5 REST endpoint,
no FIX gateway in the retail product, and no documented wire protocol. Retail
brokers on MT5 generally expose nothing of their own either.

So:

| | |
|---|---|
| ✅ A real separate `.exe` with its own UI, process, database and logic | yes |
| ✅ Runs on your desktop, not inside a chart window | yes |
| ✅ No MQL5, no MetaEditor, no EA attached to anything | yes |
| ⚠️ MetaTrader 5 must be **running in the background** as the gateway | unavoidable |
| ❌ Fully independent of MetaTrader | **not possible** for a retail MT5 account |

MetaTrader ends up as a headless quote-and-execution service. You never look at
it. But it has to be there, and any tool claiming otherwise for a retail MT5
broker is either using an unsupported channel or not doing what it says.

**Everything except live broker access runs with no MetaTrader at all** — the
full analysis pipeline, the risk engine, the backtest, the UI and the entire
test suite. That is a deliberate architectural property, not a fallback.

[mt5pkg]: https://pypi.org/project/MetaTrader5/

## Install

```powershell
pip install -r requirements.txt
python -m alikhande doctor      # says exactly what this machine can and cannot do
python -m alikhande ui          # launch
```

Build a standalone executable:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
# -> dist\AlikhandeScanner\AlikhandeScanner.exe
```

The build script runs the test suite first and refuses to package a red build.

Before connecting to a broker: start MetaTrader 5, log in to a **demo** account,
enable Algo Trading (Tools → Options → Expert Advisors), and add your symbols to
Market Watch.

## Safety policy

Structural, not configurable:

- **Real accounts are refused, three times over.** `ExecState` has no live-trading
  mode; `core.execution` returns `REAL_ACCOUNT_BLOCKED` on any non-demo account;
  and the MT5 adapter refuses again in `send_order` through code that shares
  nothing with the first check. Deleting one does not disable the others.
- **One order boundary.** Only `core/execution.py` may call `send_order`. A test
  scans the package and fails if any other module so much as mentions it.
- **No single action can send.** Demo execution requires Arm, then Confirm, on
  separate controls, within a 20-second TTL. Re-planning under the operator
  invalidates the arming even when the plan id is unchanged.
- **An unresolved execution blocks everything.** If the broker cannot account
  for an order across positions, working orders, order history *and* deal
  history, the execution stays non-terminal, the submit gate stays shut, and it
  stays shut across a restart. Only a typed operator acknowledgement clears it.
- **A rule score is not a probability.** Historical win rate appears only above
  30 real outcomes for that symbol, setup and rule version — always with its
  Wilson interval and sample size, or not at all.
- **No martingale, grid, recovery or averaging down.**

## Layout

```
alikhande/
  core/        pure logic — imports no MT5, no Qt, no sqlite
    indicators, trend, zones, regime, spread, signals
    risk, portfolio, guards, preflight, execution, arming
    outcomes, statistics, lifecycle, calendar_gate, runtime
    ports.py   the Protocols everything outside core implements
  adapters/
    mt5/       live gateway (Windows + running terminal)
    offline/   deterministic in-memory gateway for replay and offline use
    sqlite/    schema, migrations, repositories
  app/         scan orchestrator, backtest engine
  ui/          PySide6 five-tab window, theme, worker thread
tests/         180 tests, stdlib unittest, no MetaTrader required
packaging/     PyInstaller spec and Windows build script
```

`core` depends on nothing outside itself. That is what lets the whole pipeline
be tested here, and it is the single biggest difference from the MQL5 build.

## Backtest

```powershell
# synthetic bars — proves the machinery, evidence about nothing
python -m alikhande backtest --symbols EURUSD,XAUUSD

# real bars exported from MetaTrader (Ctrl+S on a chart -> SYMBOL_TIMEFRAME.csv)
python -m alikhande backtest --data C:\exports --symbols EURUSD --database bt.sqlite
```

The backtest calls the same `SignalEngine`, `RiskPlanner` and `OutcomeTracker`
the live app uses — it does not have its own copy of the strategy. Look-ahead is
prevented structurally: the gateway's cursor truncates every series, so an
engine asking for 300 bars cannot receive a bar the replay has not reached, and
higher timeframes advance proportionally so H1 cannot leak past M5.

Every report states its own limits: bar-resolution fills (a bar spanning both
stop and target is scored a **stop**), no commission or slippage model, and a
blunt warning when the data is synthetic.

## Status

**Executed and passing:** 180 tests, covering the indicators, all analysis
engines, position sizing, portfolio risk, the arming protocol, the calendar
gate, the SQLite schema against real sqlite3, the outcome loop end to end, and
every safety gate above. The UI has been constructed, run and rendered
headlessly. A 95,600-bar backtest completes and its arithmetic reconciles.

**The outcome loop is closed.** This is the gap the MQL5 build never filled:
there, `SaveOutcome` was defined and called by nothing, so `outcomes` stayed
empty and every probability rendered "n/a" forever. Here, `core/outcomes.py`
tracks an active signal to its TP or SL and records realised R, MFE and MAE, and
a backtest run writes 1,247 outcomes that the statistics layer reads back.

**Not verified:**

- **Live broker access.** No Windows machine and no MetaTrader terminal existed
  where this was built. `adapters/mt5/gateway.py` has never executed.
- **Indicator agreement with MetaTrader.** The formulas follow MetaTrader's
  published sources — including that MT5's ATR is a *simple* average of True
  Range, not Wilder smoothing — but that agreement is derived from documentation,
  not measured. This is why the desktop build carries its own `RULE-2.0.0-PY`
  version: its outcomes are never pooled with the EA's.
- **Strategy edge. Not established, and not claimed.** There is no out-of-sample
  result on real data. The synthetic backtest's win rate is an artifact of a
  generator whose trend component is a sum of sine waves and is therefore
  predictable in a way no market is.

See `docs/VERIFICATION.md` for the full accounting.
