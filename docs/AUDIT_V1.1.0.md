# Audit — v1.1.0 baseline

Source: `baseline/v1.1.0-verified-drive`, all 31 files verified against
`MANIFEST.sha256` (31 OK / 0 FAILED) independently before the audit began.

Bug identifiers are referenced from commit messages and `docs/TRACEABILITY.md`.

## Correctness defects

### B1 — uninitialised alert cooldown
`AlikhandeScanner.mq5:49` resizes `g_last_alert` and never initialises it. MQL5
does not guarantee zero-fill on `ArrayResize`, so the first cooldown comparison
per symbol reads an undefined `datetime`. Alerts are then either suppressed for
an arbitrary period or fired on every pass. **Found independently by the static
gate (`RESIZE_WITHOUT_INIT`).**

### B2 — signals displayed against a stale price
`AlikhandeScanner.mq5:66-70`. The whole candidate — entry, stop, target and the
zone-proximity decision — is computed once per closed bar and cached. It is then
displayed, alerted and logged against a *live* quote until the next bar closes.
On M5 that is up to five minutes during which the dashboard reports LONG at an
entry the market has left. The logged entry is not the entry a human would get.
**Most severe defect in the baseline.**

### B3 — hard block leaves a phantom setup
`SignalEngine.mqh:63` sets `s.direction = AS_DIR_NONE` on a hard block but leaves
`s.setup` populated, so a blocked candidate still advertises a setup type.

### B4 — indicator handles created per call
`TrendEngine.mqh:13-18` and `ZoneEngine.mqh:9-10` call `iMA`/`iADX`/`iATR` and
`IndicatorRelease` on every invocation — four handles per timeframe per symbol
per closed bar. Beyond the cache churn, `BarsCalculated()` is unreliable
immediately after handle creation, so the first `Analyze()` for each symbol
routinely failed with "IND DATA" and only recovered a bar later. **Found
independently by the static gate (`UNCACHED_INDICATOR`).**

### B5 — structurally blind at the entry trigger
`SignalEngine.mqh:14-15`. `NearestZones` requires `zones[i].high <= snap.bid` for
support and `zones[i].low >= snap.ask` for resistance. When price is *inside* a
zone — precisely the pullback or rejection moment the strategy is built to catch
— both indices stay `-1`, `near_support`/`near_resistance` are false, and no
setup can qualify. The strategy cannot see its own trigger.

### B6 — supply and demand merged into one zone
`ZoneEngine.mqh:26-29` merges any two pivots whose ATR-scaled bands overlap,
regardless of whether they came from swing highs or swing lows, into a single
untyped zone with one shared `touches` counter. A band holding three highs and
three lows reports six touches. `touches` drives `quality`, and `quality`
contributes up to 15 points of signal score.

### B7 — drawdown guard disarms on restart
`AccountRiskGuard.mqh:11`. `Initialize()` sets `m_peak_equity` to *current*
equity. Restarting during a drawdown resets the high-water mark, so the total
drawdown guard silently stops guarding at the moment it matters most.
`m_consecutive_losses` is lost the same way. No state is persisted anywhere.

### B8 — foreign trades pollute risk state
`AlikhandeScanner.mq5:78`. `OnTradeTransaction` calls `RegisterClosedProfit` for
every closing deal on the account with no magic-number filter and no
de-duplication by ticket. Manual trades and other EAs' losses increment the
scanner's consecutive-loss counter and can halt it for something it never did.
MetaQuotes documents that transaction delivery is unordered, may repeat, and can
be dropped on queue overflow, so the accounting is unreliable in both directions.

### B9 — four unreachable modules
`AS_RiskPlanner`, `AS_DemoExecution`, `AS_NewBarDetector` and `AS_Statistics` are
included and compiled but never instantiated in the EA. The Wilson interval
implementation is correct and was never called; the risk planner is unreachable,
so no sizing ever happened.

### B10 — freeze level read and ignored
`TradeGuards.mqh:14-17` checks `SYMBOL_TRADE_STOPS_LEVEL` only.
`SYMBOL_TRADE_FREEZE_LEVEL` is read into the spec struct and never used. Inside
the freeze band the server refuses modification and closure — a materially
different failure mode from a too-tight stop.

### B11 — stale quote reported as success
`MarketData.mqh:28` returns `true` for a stale tick, relying on one downstream
check in the signal engine to catch it. Correct today; silently wrong the moment
a second consumer is added.

### B12 — dashboard layout defects
`Dashboard.mqh`. Rows are laid out with printf column padding (`%-12s | %7.1f`)
and rendered in the default proportional font, so columns never align. Buttons
are pinned at absolute `x=780`, landing off-screen on a narrower window. No
background panel, so the text competes with the chart behind it.

## Architectural gaps

- No persistence beyond appended CSV. The de-duplication registry is a RAM array,
  so a restart re-logs signals already recorded.
- No outcome tracking, therefore no possibility of a real win rate.
- No aggregate exposure. Risk is per-trade and per-symbol only, which misses
  correlated concentration (three long dollar-shorts are one bet, not three).
- No `OrderCheck` preflight, no execution state machine, no reconciliation.
- No tests of any kind.
- Code style is single-line and dense throughout, which is a maintainability
  hazard independent of correctness.

## What the baseline got right and v1.2.0 keeps

Not everything needed changing, and these were kept deliberately:

- The symbol resolution ladder — exact, `_o` suffix, `#` prefix, then a
  normalised scan of the full broker tree. Broker-tested and correct.
- Spread classification against the symbol's own rolling median rather than an
  absolute point threshold.
- The ATR quality ratio as a volatility-regime gate.
- The `[ASSUMED]` tagging discipline in `Config.mqh`, separating validated values
  from working hypotheses.
- Structural stops placed beyond the zone edge, the 2R minimum, and the
  opposing-zone veto on room-to-target.
- The EMA chronology fix and the directional-strength fix, both real corrections
  that v1.2.0 preserves and additionally enforces structurally.
- Rejecting a trade whose risk budget buys less than the broker minimum lot,
  rather than rounding up and silently inflating risk.
- `has_historical_estimate = false` as an explicit honesty flag.
- The sliced scheduler with a processing budget.
