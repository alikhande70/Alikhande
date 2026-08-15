# Alikhande Scanner Desktop 2.2.0

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
Market Watch. Live Demo/Shadow also requires the covered operator calendar at
`%LOCALAPPDATA%\AlikhandeScanner\calendar.csv`; see
[`docs/WINDOWS_INSTALL.md`](docs/WINDOWS_INSTALL.md) for its exact format.

## The three environments

Declared, not inferred. Each carries a capability matrix computed from its name
on every read rather than stored, so nothing holding a reference can mutate it.

| | Data | Database | Can send? |
|---|---|---|---|
| **Backtest** | recorded or synthetic bars | `replay_*.sqlite` | never — no broker |
| **Demo** | a live terminal, demo account | `alikhande.sqlite` | yes, after Arm **and** Confirm |
| **Production** | a live terminal, real account | `production.sqlite` | **hard-locked** |

Production runs everything short of the send: connection supervision, data
quality, sizing against real contract specifications, preflight, reconciliation,
recovery and reporting. That is the point — production readiness is measured
rather than assumed.

The lock is not a setting. `capabilities()` returns a hard `False` for
production rather than deriving it from the module constant, so finding the
constant and flipping it changes nothing; a test does exactly that and asserts
it changed nothing. There is no code path that opens it. If real trading is ever
authorised it arrives as its own reviewed change.

Routing is by the **declared** environment, not by the runtime kind. A demo
session and a production session are both `RuntimeKind.LIVE` and would otherwise
share one database — which is precisely the contamination the original routing
exists to prevent.

## The robot

Everything a person should not have to do by hand, and nothing more. It watches
session windows (in broker server time, never local), rotates symbols, keeps the
link alive, takes verified backups, escalates health, pauses itself when the
account says stop, and queues qualified candidates with their evidence already
assembled.

**It does not arm and it does not confirm.** Execution requires two deliberate
human actions on separate controls; an autopilot performing either one would not
weaken that gate, it would remove it, because a single click would then be
enough to send an order. `RobotDecision` has no arm/confirm/send field at all,
and a test asserts it never grows one.

The reverse direction is unrestricted: it may disarm, cancel, pause and stop on
its own at any time. Actions that reduce exposure need no ceremony; only actions
that create it do.

## Reliability

Six subsystems for the things that only matter on a bad day. Each is pure and
*decides* rather than acts, so a six-hour flapping link can be tested in
milliseconds instead of against a terminal nobody has.

- **Connection supervision.** Health is inferred from what the gateway did, not
  read from it. The state that matters is `STALLED` — every call answering,
  every call fast, every call returning the same server time. That is the normal
  shape of a broken MT5 session, and a boolean `is_connected()` reports it as
  healthy forever.
- **Data quality.** Per-pass refusals are correct and forgettable; only the
  accumulated record can distinguish a symbol still downloading from one the
  broker does not serve.
- **Order errors.** Every retcode classified by whose problem it is and whether
  an identical retry could plausibly succeed. No `REQUEST`-category error is
  retryable, and an unrecognised code is `UNKNOWN` and not retryable rather than
  being given a plausible category.
- **Crash recovery.** Sessions, detected by absence: a record still holding
  `closed_at == 0` means nobody ran the shutdown path. A crash holding an
  in-flight order outranks a plain crash.
- **Notifications.** Routed by consequence rather than log level, throttled per
  subject so a chatty subject cannot crowd out a quiet important one. Critical is
  never throttled.
- **Backup, restore, diagnostics.** Backups use SQLite's online backup API and
  are verified by being read back — an unverified backup is a file with a
  reassuring name. Restore moves the current database aside instead of
  overwriting it, and deletes nothing, ever.

## Safety policy

Structural, not configurable:

- **Real-account sends are refused independently.** Production exposes
  Alert-only and Shadow rehearsal, but no sending mode. `core.execution`
  refuses Demo Confirm on a non-demo account immediately before the sole send,
  and the MT5 adapter refuses again inside `send_order` through independent
  code. Shadow returns before that boundary and is stored as non-scorable
  `SHADOW/PREFLIGHT_ONLY` evidence.
- **One order boundary.** Only `core/execution.py` may call `send_order`. A test
  scans the package and fails if any other module so much as mentions it.
- **No single action can send.** Demo execution requires Arm, then Confirm, on
  separate controls, within a 20-second TTL. Re-planning under the operator
  invalidates the arming even when the plan id is unchanged.
- **An unresolved execution blocks everything.** If the broker cannot account
  for an order across positions, working orders, order history *and* deal
  history, the execution stays non-terminal, the submit gate stays shut, and it
  stays shut across a restart. Only a typed operator acknowledgement clears it.
- **The GUI owns no live state.** MT5, SQLite and `ScanEngine` are constructed,
  used and closed by `ScanWorker`; Qt receives deep-copied snapshots and posts
  queued intents.
- **Attribution is exact.** Broker truth uses execution correlation, tickets and
  position identity, never magic+symbol. Conflicts and netting contamination
  become blocking `UNKNOWN`, not a plausible outcome. Failed position/order
  reads stay visibly unknown in the UI; they are never painted as empty broker
  state. Mixed or missing close reasons are non-scorable `CLOSED`, never an
  inferred TP/SL.
- **Replay publication is atomic.** Cancel, error and copy failure preserve the
  previous valid replay sample; only a finished staged run replaces it.
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
    environment  the three environments and their capability matrix
    supervision  connection health, reconnect policy
    dataquality  bar gaps, staleness, chronic-failure accumulation
    order_errors retcode taxonomy: whose problem, and is a retry worth it
    recovery     sessions, crash detection, what to restore
    notifications what is worth interrupting somebody for
    robot        session windows, autopilot policy, the execution lock
    ports.py     the Protocols everything outside core implements
  adapters/
    mt5/       live gateway (Windows + running terminal)
    offline/   deterministic in-memory gateway for replay and offline use
    sqlite/    schema, migrations, repositories
  app/         scan orchestrator, backtest engine, maintenance
  ui/          PySide6 window: theme, motion, icons, eleven views
tests/         full unittest suite, no MetaTrader required
               fake_mt5.py    a terminal double, so the live adapter executes
packaging/     PyInstaller spec and Windows build script
```

## Design system

Colour is spent only on meaning; **depth** carries structure. Five surface steps
from the window plane to a raised popover, each with its own border, so
hierarchy is visible without tinting anything.

Four jobs qualify for colour, and nothing else on screen is tinted:

- **Direction** — LONG/SHORT, always with an arrow and a word beside the hue.
- **State** — the fixed status palette. Warning and serious share a warm family
  by design, so every status colour ships with an icon and a text label;
  `StatusChip` takes both as required arguments.
- **Magnitude** — a *neutral* ramp for a rule score, because a saturated ramp
  makes it look like a probability read off a calibrated instrument.
- **Interaction** — one indigo, on the active nav indicator, focus ring, primary
  action and selected row. Indigo rather than blue because LONG is already a
  blue, and a focus ring and a direction column are both read peripherally.

Motion is tied to state changes only: nothing animates on first paint, no
animated value ever tweens its own digits, and every animation replaces rather
than queues — passes land every 250 ms and a queueing animation falls further
behind the data on each one.

Persian is right-to-left throughout, with one deliberate exception: **the price
chart never mirrors.** RTL flips reading order, not time, and a mirrored uptrend
looks like a downtrend to anybody who has seen a chart.

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

`STATIC_CANDIDATE`: the full local suite covers indicators, analysis, position
sizing, portfolio risk, arming, covered-calendar fail-closed behaviour, schema
v4 on real sqlite3, exact Demo outcome reconstruction, Shadow provenance and
atomic replay replacement. The UI is constructed and rendered headlessly.
Final acceptance remains `BLOCKED` until Windows + real MT5 gates run.

**The outcome loop is closed.** This is the gap the MQL5 build never filled:
there, `SaveOutcome` was defined and called by nothing, so `outcomes` stayed
empty and every probability rendered "n/a" forever. Here replay outcomes carry
realised R/MFE/MAE, while Demo outcomes are rebuilt from exact broker deals and
leave unavailable MFE/MAE as null. TP/SL comes only from the broker close reason;
other exact closes are non-scorable `CLOSED`.

**Runtime gates still blocked:**

- **Live broker access, against a real terminal.** The adapter now *executes* —
  against `tests/fake_mt5.py`, a double for the MetaTrader5 module surface it
  uses — which is how a defect that broke every live pass was finally found: the
  gateway attached on the UI thread and the scan worker's every call was then
  refused by the package's owner-thread guard, silently, reported as
  "disconnected". What is still unproven is that MetaQuotes' package behaves as
  the double models it. That closes on Windows and nowhere else.
- **Indicator agreement with MetaTrader.** The formulas follow MetaTrader's
  published sources — including that MT5's ATR is a *simple* average of True
  Range, not Wilder smoothing — but that agreement is derived from documentation,
  not measured. This is why the desktop build carries its own `RULE-2.0.0-PY`
  version: its outcomes are never pooled with the EA's.
- **Strategy edge. Not established, and not claimed.** There is no out-of-sample
  result on real data. The synthetic backtest's win rate is an artifact of a
  generator whose trend component is a sum of sine waves and is therefore
  predictable in a way no market is.

See `docs/E2E_FINAL_AUDIT_PR6.md` for the final path audit and
`docs/VERIFICATION.md` for the qualification boundary.
