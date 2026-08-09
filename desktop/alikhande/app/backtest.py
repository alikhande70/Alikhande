"""Backtest by replaying bars through the real pipeline.

The design rule that makes this worth trusting at all: **the backtest does not
have its own copy of the strategy.** It advances a cursor on an
``OfflineGateway`` and calls the same ``SignalEngine``, the same ``RiskPlanner``
and the same ``OutcomeTracker`` the live app uses. A backtest that reimplements
the logic tests the reimplementation.

Look-ahead is prevented structurally rather than by care: the gateway's cursor
truncates every series, so an engine asking for 300 bars physically cannot
receive a bar the replay has not reached. Higher timeframes advance
proportionally, so H1 cannot reveal a bar M5 has not seen either.

Three honesty rules the report enforces on itself, because a backtest that
overstates itself is worse than none:

1. **Bar-resolution fills.** With OHLC and no ticks, a bar that spans both the
   stop and the target is resolved as a **stop**. Assuming the favourable order
   inflates every result containing a volatile bar.
2. **No spread/slippage model beyond the configured spread.** Entries are taken
   at the synthetic quote, which is optimistic against a real fill.
3. **Synthetic data is not evidence.** When the bars came from the generator
   rather than a broker export, ``data_source`` says so and every derived
   number is labelled as describing the machinery, not a market.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..config import AppConfig
from ..core.enums import Direction, RuntimeKind, SetupType, SignalState, Timeframe
from ..core.features import extract as extract_features
from ..core.hashing import fnv1a
from ..core.journal import Journal
from ..core.models import Bar, Outcome, RuntimeContext, SymbolSnapshot
from ..core.outcomes import OutcomeTracker
from ..core.risk import RiskPlanner
from ..core.signals import SignalEngine
from ..core.spread import SpreadTracker
from ..core.statistics import wilson
from ..adapters.offline.gateway import OfflineGateway
from ..version import RULE_VERSION, SCORING_VERSION, VERSION

BACKTEST_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.H1,
    Timeframe.H4,
)


@dataclass
class BacktestResult:
    run_id: str = ""
    data_source: str = "synthetic"
    symbols: tuple[str, ...] = ()
    bars_replayed: int = 0
    elapsed_seconds: float = 0.0

    signals_evaluated: int = 0
    candidates: int = 0
    confirmed: int = 0
    planned: int = 0
    rejected_by_risk: int = 0

    trades: int = 0
    wins: int = 0
    losses: int = 0
    sum_r: float = 0.0
    max_drawdown_r: float = 0.0
    outcomes: list[Outcome] = field(default_factory=list)
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    setups: dict[str, int] = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def expectancy_r(self) -> float:
        return self.sum_r / self.trades if self.trades else 0.0

    def confidence_interval(self) -> tuple[float, float] | None:
        """Wilson interval on the win rate, or ``None`` below any usable sample.

        Returned rather than a bare percentage for the same reason the live
        statistics layer does it: a win rate without its interval and sample
        size invites a conclusion the data cannot support.
        """
        return wilson(self.wins, self.trades)

    def report(self, min_sample: int = 30) -> str:
        lines: list[str] = []
        add = lines.append

        add("=" * 72)
        add(f"  Alikhande Scanner Desktop {VERSION} — backtest report")
        add("=" * 72)
        add(f"  run id           {self.run_id}")
        add(f"  data source      {self.data_source}")
        add(f"  symbols          {', '.join(self.symbols)}")
        add(f"  bars replayed    {self.bars_replayed:,}")
        add(f"  wall clock       {self.elapsed_seconds:.2f}s")
        add(f"  rule version     {RULE_VERSION}")
        add(f"  scoring version  {SCORING_VERSION}")
        add("")
        add("  PIPELINE")
        add(f"    evaluations            {self.signals_evaluated:,}")
        add(f"    candidates             {self.candidates:,}")
        add(f"    confirmed signals      {self.confirmed:,}")
        add(f"    plans built            {self.planned:,}")
        add(f"    refused by risk/sizing {self.rejected_by_risk:,}")
        if self.setups:
            add("    setups: " + ", ".join(f"{k}={v}" for k, v in sorted(self.setups.items())))
        if self.rejection_reasons:
            add("    top refusals:")
            top = sorted(self.rejection_reasons.items(), key=lambda kv: -kv[1])[:8]
            for reason, count in top:
                add(f"      {count:6,}  {reason}")
        add("")
        add("  OUTCOMES")
        add(f"    resolved trades  {self.trades:,}")
        if self.trades:
            add(f"    wins / losses    {self.wins:,} / {self.losses:,}")
            add(f"    win rate         {self.win_rate * 100:.1f}%")
            interval = self.confidence_interval()
            if interval:
                add(
                    f"    95% Wilson       [{interval[0] * 100:.1f}%, {interval[1] * 100:.1f}%]"
                )
            add(f"    total R          {self.sum_r:+.2f}")
            add(f"    expectancy       {self.expectancy_r:+.3f} R / trade")
            add(f"    max drawdown     {self.max_drawdown_r:.2f} R")
        else:
            add("    no trade resolved")
        add("")
        add("  WHAT THIS DOES AND DOES NOT ESTABLISH")

        if self.trades == 0:
            add("    * No trade resolved, so this run says NOTHING about the strategy.")
            add("      It exercised the pipeline end to end and nothing more.")
        elif self.trades < min_sample:
            add(
                f"    * {self.trades} trades is below the {min_sample}-sample policy floor."
            )
            add("      The win rate above is printed for diagnostics ONLY. It is not")
            add("      an estimate of edge and must not be quoted as one.")
        else:
            add(f"    * {self.trades} resolved trades clears the {min_sample}-sample floor,")
            add("      but sample size alone does not make a result out-of-sample.")

        if self.data_source == "synthetic":
            add("    * DATA IS SYNTHETIC. These bars came from a seeded generator, not")
            add("      from a broker. Every number above describes whether the software")
            add("      works. NONE of it is evidence about any real market, and no")
            add("      profitability claim may be drawn from it.")
            add("    * The generator's trend component is a SUM OF SINE WAVES, so its")
            add("      price series is autocorrelated by construction — the next move is")
            add("      genuinely predictable from the last one in a way no market is.")
            add("      A trend-pullback strategy will therefore score far better here")
            add("      than on real data. TREAT A HIGH WIN RATE ON THIS DATA AS A SIGN")
            add("      THE PIPELINE RUNS, NOT AS A SIGN THE STRATEGY WORKS.")
        else:
            add("    * Data is a broker export. Results are in-sample unless a separate")
            add("      out-of-sample window was held back and tested after the fact.")

        add("    * Fills are resolved at bar resolution. A bar touching both the stop")
        add("      and the target is scored as a STOP, since tick order is unknowable.")
        add("    * No commission, swap or slippage model beyond the configured spread.")
        add("=" * 72)
        return "\n".join(lines)


class Backtester:
    def __init__(self, config: AppConfig | None = None, journal: Journal | None = None) -> None:
        self._config = config or AppConfig()
        self._journal = journal or Journal()

    def run(
        self,
        gateway: OfflineGateway,
        symbols: tuple[str, ...],
        *,
        warmup_bars: int = 400,
        max_steps: int | None = None,
        step: int = 1,
        data_source: str = "synthetic",
        repositories=None,
        run_id: str = "",
    ) -> BacktestResult:
        """Replay ``gateway``'s M5 series through the live pipeline.

        ``warmup_bars`` is skipped before anything is evaluated — the indicators
        need a slow EMA and an ATR median window before their output means
        anything, and scoring on a half-warmed indicator is noise dressed as
        signal.
        """
        started = time.perf_counter()
        engine = SignalEngine(self._config)
        planner = RiskPlanner(self._config)
        tracker = OutcomeTracker()
        spread_trackers = {s: SpreadTracker(self._config.scan) for s in symbols}

        result = BacktestResult(
            run_id=run_id or fnv1a(f"backtest|{time.time()}"),
            data_source=data_source,
            symbols=symbols,
        )

        base_tf = Timeframe.M5
        total = min(gateway.series_length(s, base_tf) for s in symbols)
        end = total if max_steps is None else min(total, warmup_bars + max_steps)

        contexts: dict[str, object] = {}
        last_structure_bar: dict[str, int] = {}
        equity_r = 0.0
        peak_r = 0.0

        for cursor in range(warmup_bars, end, max(1, step)):
            gateway.set_cursor(cursor)
            now = gateway.server_time()

            for symbol in symbols:
                spec = gateway.symbol_spec(symbol)
                tick = gateway.tick(symbol)
                if spec is None or tick is None:
                    continue

                m5 = gateway.bars(symbol, base_tf, self._config.scan.minimum_bars)
                if len(m5) < 2:
                    continue

                # ---- resolve open trades on the bar that just closed ---------
                for outcome, state in tracker.update(symbol, m5[-1], now):
                    result.outcomes.append(outcome)
                    result.trades += 1
                    result.sum_r += outcome.realized_r
                    if state == SignalState.TP:
                        result.wins += 1
                    else:
                        result.losses += 1
                    equity_r += outcome.realized_r
                    peak_r = max(peak_r, equity_r)
                    result.max_drawdown_r = max(result.max_drawdown_r, peak_r - equity_r)
                    if repositories is not None:
                        repositories.save_outcome(outcome)
                        repositories.update_signal_state(outcome.signal_id, state)

                # ---- snapshot ------------------------------------------------
                snapshot = SymbolSnapshot(
                    requested_symbol=symbol,
                    symbol=symbol,
                    bid=tick.bid,
                    ask=tick.ask,
                    point=spec.point,
                    digits=spec.digits,
                    tick_time=tick.time,
                )
                spread_points = (tick.ask - tick.bid) / spec.point
                snapshot.spread_points = spread_points
                spread = spread_trackers[symbol]
                spread.add(spread_points)
                (
                    snapshot.spread_state,
                    snapshot.spread_ratio,
                    snapshot.spread_percentile,
                ) = spread.classify(spread_points)

                # ---- structure, rebuilt only on a new closed bar --------------
                closed_time = m5[-2].time
                if last_structure_bar.get(symbol) != closed_time:
                    last_structure_bar[symbol] = closed_time
                    bars_by_tf = {
                        tf: gateway.bars(symbol, tf, self._required(tf))
                        for tf in BACKTEST_TIMEFRAMES
                    }
                    contexts[symbol] = engine.build_context(
                        symbol, bars_by_tf, snapshot, now=now
                    )

                context = contexts.get(symbol)
                if context is None or not context.valid:  # type: ignore[union-attr]
                    continue

                # ---- evaluate -------------------------------------------------
                signal = engine.evaluate(context, snapshot, now)  # type: ignore[arg-type]
                result.signals_evaluated += 1

                if signal.state == SignalState.CANDIDATE:
                    result.candidates += 1
                for code in signal.validation_codes:
                    key = code.split("(")[0]
                    result.rejection_reasons[key] = result.rejection_reasons.get(key, 0) + 1

                if signal.direction == Direction.NONE or signal.hard_blocked:
                    continue

                result.confirmed += 1
                if signal.setup != SetupType.NONE:
                    name = signal.setup.name
                    result.setups[name] = result.setups.get(name, 0) + 1

                # One open trade per symbol, as the live guards enforce.
                if tracker.is_tracking(signal.signal_id) or any(
                    t.symbol == symbol for t in tracker.tracked.values()
                ):
                    continue

                account = gateway.account()
                plan = planner.build(
                    signal,
                    gateway=gateway,
                    account=account,
                    spec=spec,
                    own_positions=[],
                    specs={symbol: spec},
                    now=now,
                )
                if not plan.valid:
                    result.rejected_by_risk += 1
                    for code in plan.validation_codes:
                        key = "PLAN_" + code.split("(")[0]
                        result.rejection_reasons[key] = result.rejection_reasons.get(key, 0) + 1
                    continue

                result.planned += 1
                if repositories is not None:
                    repositories.save_signal(signal, result.run_id)
                    repositories.save_features(
                        signal.signal_id, extract_features(context, signal, snapshot)
                    )
                    repositories.save_plan(plan)
                    repositories.update_signal_state(signal.signal_id, SignalState.ACTIVE)
                tracker.open(signal, plan.entry, now)

            result.bars_replayed += 1

        result.elapsed_seconds = time.perf_counter() - started
        return result

    def _required(self, timeframe: Timeframe) -> int:
        return max(
            self._config.scan.minimum_bars,
            self._config.structure.zone_lookback_bars + 20,
            260,
        )


def backtest_runtime(session: str = "backtest") -> RuntimeContext:
    """A replay runtime — never production, whatever else is attached."""
    return RuntimeContext(
        kind=RuntimeKind.REPLAY,
        is_production=False,
        session_identity=fnv1a(session),
        description="replay",
    )
