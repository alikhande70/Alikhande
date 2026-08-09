# Verification status — Desktop 2.0.0

Being precise about what has and has not been established matters more here than
anywhere else in the project: this is a system whose entire purpose is to stop
people trusting unverified claims. Applying that to its own build is the minimum
consistency requirement.

## What changed from the MQL5 build

The MQL5 tree was **statically verified and runtime unproven** — no MetaEditor
and no terminal existed where it was written, so nothing had ever executed. A
purpose-built MQL5 static analyser stood in for a compiler.

The desktop port removes that limitation for everything except live broker
access, because the pure core imports nothing external. The analysis engines,
the risk model, the execution state machine, the persistence layer and the
backtest all **run**, and 180 tests assert their behaviour.

That change is not free. It introduces one new unverified claim of its own —
indicator agreement — which is recorded below rather than glossed over.

## VERIFIED — executed in this environment

### The test suite
180 tests, stdlib `unittest`, no external dependency:

```
python -m unittest discover -s tests -t .
Ran 180 tests — OK
```

Covering:

- **Indicators.** EMA seeding, ATR as a simple average of True Range, ADX range
  and warm-up index, median semantics, `None` propagation for unwarmed values.
- **Trend.** Refusal on short history, bullish/bearish scoring, the forming bar
  being dropped, `available_information_time` landing on the bar close, and the
  two-sided-strength bug staying fixed.
- **Zones.** The three-way relation including `UNAVAILABLE`, type-correct
  anchoring, a zone price is *inside* remaining findable, confirmation lag.
- **Risk.** Refusal below the broker minimum lot rather than rounding up,
  round-down normalisation, refusal when the broker cannot price the stop,
  policy ceilings, aggregate and per-currency caps.
- **Unbounded risk.** A stopless position is reported unbounded and blocks all
  new risk *before* any cap is consulted.
- **Execution.** Every reconciliation source, and the P0 below.
- **Idempotency.** A replayed deal ticket does not inflate filled volume, in
  memory and across a database reopen.
- **Arming.** Confirm-without-arm, expiry, superseded plan, and a re-planned
  plan with an unchanged id.
- **Calendar.** `UNKNOWN` never reads as `CLEAR`; blocks in production, does not
  block in replay but is flagged NEWS-BLIND.
- **Persistence.** Real sqlite3: migration, idempotent re-migration, refusal of
  a newer schema, deal admission surviving a reopen, outcome scoping by rule
  version, and a corrupt execution state loading as `UNKNOWN` (gate shut) rather
  than as finished.
- **Outcomes.** ±R scoring, MFE/MAE, and the conservative both-touched rule.

### The single-order-boundary property
Asserted mechanically, not by convention: a test walks every `.py` file in the
package and fails if `send_order` is referenced outside `core/execution.py`,
`core/ports.py` and the adapters.

### The P0: an unresolved execution never releases the gate
Directly tested. An order whose retcode is unrecognised becomes `UNKNOWN`; with
every broker source silent past the grace period it stays **non-terminal**;
`has_unresolved()` stays true; the next submit is refused; a fresh engine
restoring the stored record is still blocked; and only a non-empty operator note
clears it. A resolver that raises is treated as *no answer*, not as absence.

### The UI
Constructed, shown, run through its event loop and rendered to images headlessly
(`QT_QPA_PLATFORM=offscreen`). Five tabs build, the worker thread runs scan
passes, and snapshots render. **Not** verified: appearance on a real Windows
desktop, high-DPI scaling, or any user interaction.

### The backtest
95,600 bars across EURUSD and XAUUSD replayed end to end. 1,247 trades resolved;
`2 × wins − losses` reconciles exactly with total R; 1,247 outcome rows written
and read back through the statistics layer.

### The outcome loop is closed
`core/outcomes.py` tracks an ACTIVE signal to TP or SL and writes realised R,
MFE and MAE. `outcome_counts` returns real samples, and above the 30-sample
floor `has_historical_estimate` becomes true and a Wilson interval is rendered.
In the MQL5 build this was permanently false.

## NOT VERIFIED

### Live broker access — NOT VERIFIED
`adapters/mt5/gateway.py` has **never executed**. No Windows machine and no
MetaTrader terminal existed where this was built; the `MetaTrader5` package is
Windows-only and cannot even be imported here. Specifically unproven: attaching
to a terminal, symbol resolution against real broker decoration, `order_check`
retcodes, filling-mode selection, `order_calc_profit` on cross-currency pairs,
and `order_send` against a real demo server.

Everything the gateway feeds is tested against a stub implementing the same
Protocol, so the *contract* is exercised. Whether MetaTrader honours it as
documented is not established.

### Indicator agreement with MetaTrader — NOT VERIFIED
This is the desktop build's own new risk, and it did not exist in the EA.

The EA read MetaTrader's indicator buffers. This computes EMA, ATR and ADX in
Python, following MetaTrader's published indicator sources — including the
detail that **MT5's ATR is a simple moving average of True Range**, not the
Wilder smoothing MT4 used. That reading is from documentation. It has not been
compared against a running terminal.

The mitigation is structural rather than hopeful: the desktop build stamps
`RULE-2.0.0-PY`, and the statistics layer scopes every sample by rule version,
so desktop and EA outcomes can never be pooled even if someone points both at
one database.

Verifying it needs one afternoon on a Windows box: export bars, run the same
periods through `iMA`/`iATR`/`iADX`, and diff.

### PyInstaller packaging — NOT VERIFIED
`packaging/alikhande.spec` and `build_windows.ps1` have not been run. PyInstaller
does not cross-compile, so a Windows executable cannot be produced or tested
from Linux. The spec is written from PyInstaller's documented behaviour.

### Strategy edge — NOT VERIFIED, AND NOT CLAIMED
There is no out-of-sample result, no walk-forward and no live record on real
data.

The synthetic backtest reports a 74.1% win rate. **This is not evidence of
anything.** The generator's trend component is a sum of sine waves, so the
series is autocorrelated by construction and a trend-pullback strategy will
exploit it trivially. The number measures the generator, not the market. The
report says so on every run, in those words.

**Nothing in this repository constitutes evidence that the strategy is
profitable.** The persistence layer exists precisely so that this can eventually
be answered with data instead of opinion — and now, unlike in the MQL5 build,
the machinery to collect that data actually works.

## A defect found by running the code

Worth recording, because it is the clearest argument for the port.

The backtest's first run reported 1,197 wins, 8,444 losses and a total of
**+8,130 R**. With a 2R target those numbers cannot coexist: 1,197 × 2 − 8,444 =
−6,050. The contradiction was in the data, not the arithmetic — 76 trades
labelled `SL` had returned **+1.0 R**.

The cause: `find_nearest_zone` deliberately does not require a zone to sit on one
side of price (that was the v1.1.0 fix which made the INSIDE case findable). So
when price traded *below* a demand zone, a LONG took `stop = zone.low - buffer`,
which is **above** its entry — an inverted trade whose stop and target both sit
in the same direction. `abs(entry - stop)` then hid it from the distance check,
and every downstream gate passed it.

**The identical defect exists in the MQL5 build** and has been fixed there too
(`STOP_ON_WRONG_SIDE_OF_ENTRY`, plus relation-aware zone anchoring). The static
analyser could never have found it: the code is well-formed, every identifier
resolves, and nothing is unreachable. It took executing it and checking that the
results were arithmetically possible.

## Required next steps

1. On Windows with MT5 running: `python -m alikhande doctor`. Gate: terminal
   reachable, Algo Trading enabled, account reported DEMO.
2. Run `python -m alikhande ui` against a demo account in **Alert-only** mode.
   Confirm symbols resolve, spreads warm up and signals appear.
3. Verify the indicators: export bars, compare EMA/ATR/ADX against the terminal.
4. Export real history and re-run the backtest on it, holding back an
   out-of-sample window.
5. Only then Shadow mode, and only after that, demo execution.

Steps 1–2 are blocking. Until they pass, the live path is a design that has not
been shown to run.
