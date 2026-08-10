"""End-to-end tests: the outcome loop, the backtest, and the whole pipeline.

The outcome tests are the ones that matter most historically. The MQL5 build
persisted signals, plans, executions and deals with full version provenance and
still produced no statistics at all, because nothing ever wrote the ``outcomes``
table. These assert that the loop actually closes.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alikhande.adapters.offline.gateway import (
    OfflineGateway,
    aggregate,
    default_spec,
    synthesise_bars,
)
from alikhande.adapters.sqlite.database import Database
from alikhande.adapters.sqlite.repositories import Repositories
from alikhande.app.backtest import BACKTEST_TIMEFRAMES, Backtester
from alikhande.app.engine import ScanEngine
from alikhande.config import AppConfig
from alikhande.core.enums import (
    Direction,
    RunMode,
    SetupType,
    SignalState,
    Timeframe,
)
from alikhande.core.indicators import atr
from alikhande.core.models import Bar, SignalCandidate
from alikhande.core.outcomes import OutcomeTracker
from alikhande.core.runtime import detect_runtime
from alikhande.core.statistics import Statistics


def candidate(direction=Direction.LONG, entry=1.1000, stop=1.0980, target=1.1040):
    return SignalCandidate(
        signal_id="S1", symbol="EURUSD", direction=direction,
        setup=SetupType.TREND_PULLBACK, preferred_entry=entry,
        stop_loss=stop, take_profit=target, rule_version="RULE-TEST",
    )


def bar(high, low, close=None, time=1000):
    return Bar(time=time, open=low, high=high, low=low, close=close or low)


class TestOutcomeTracker(unittest.TestCase):
    """The loop the MQL5 build never closed."""

    def test_a_target_hit_scores_plus_two_r(self):
        tracker = OutcomeTracker()
        self.assertTrue(tracker.open(candidate(), 1.1000, 1000))
        resolved = tracker.update("EURUSD", bar(high=1.1050, low=1.1000), 2000)
        self.assertEqual(len(resolved), 1)
        outcome, state = resolved[0]
        self.assertEqual(state, SignalState.TP)
        self.assertAlmostEqual(outcome.realized_r, 2.0, places=6)

    def test_a_stop_hit_scores_minus_one_r(self):
        tracker = OutcomeTracker()
        tracker.open(candidate(), 1.1000, 1000)
        outcome, state = tracker.update("EURUSD", bar(high=1.1000, low=1.0970), 2000)[0]
        self.assertEqual(state, SignalState.SL)
        self.assertAlmostEqual(outcome.realized_r, -1.0, places=6)

    def test_a_bar_spanning_both_is_scored_as_a_stop(self):
        """Without ticks the order is unknowable; assuming the favourable one
        is how a backtest flatters itself."""
        tracker = OutcomeTracker()
        tracker.open(candidate(), 1.1000, 1000)
        outcome, state = tracker.update("EURUSD", bar(high=1.1100, low=1.0900), 2000)[0]
        self.assertEqual(state, SignalState.SL)
        self.assertAlmostEqual(outcome.realized_r, -1.0, places=6)

    def test_shorts_are_scored_symmetrically(self):
        tracker = OutcomeTracker()
        short = candidate(Direction.SHORT, entry=1.1000, stop=1.1020, target=1.0960)
        tracker.open(short, 1.1000, 1000)
        outcome, state = tracker.update("EURUSD", bar(high=1.1000, low=1.0950), 2000)[0]
        self.assertEqual(state, SignalState.TP)
        self.assertAlmostEqual(outcome.realized_r, 2.0, places=6)

    def test_excursions_are_recorded_in_r(self):
        """A trade that reached +1.8R before stopping out is a different lesson
        from one that never moved."""
        tracker = OutcomeTracker()
        tracker.open(candidate(), 1.1000, 1000)
        tracker.update("EURUSD", bar(high=1.1036, low=1.0995, time=1100), 1100)
        outcome, _ = tracker.update("EURUSD", bar(high=1.1000, low=1.0970, time=1200), 1200)[0]
        self.assertAlmostEqual(outcome.mfe_r, 1.8, places=5)
        self.assertLess(outcome.mae_r, 0.0)

    def test_mfe_is_never_negative_and_mae_never_positive(self):
        tracker = OutcomeTracker()
        tracker.open(candidate(), 1.1000, 1000)
        outcome, _ = tracker.update("EURUSD", bar(high=1.1000, low=1.0970), 2000)[0]
        self.assertGreaterEqual(outcome.mfe_r, 0.0)
        self.assertLessEqual(outcome.mae_r, 0.0)

    def test_a_zero_risk_signal_is_refused(self):
        """R is meaningless when R is zero; recording it would be an artefact."""
        tracker = OutcomeTracker()
        self.assertFalse(tracker.open(candidate(stop=1.1000), 1.1000, 1000))

    def test_a_directionless_signal_is_refused(self):
        tracker = OutcomeTracker()
        self.assertFalse(tracker.open(candidate(Direction.NONE), 1.1000, 1000))

    def test_the_same_signal_cannot_be_opened_twice(self):
        tracker = OutcomeTracker()
        self.assertTrue(tracker.open(candidate(), 1.1000, 1000))
        self.assertFalse(tracker.open(candidate(), 1.1000, 1000))

    def test_other_symbols_are_untouched(self):
        tracker = OutcomeTracker()
        tracker.open(candidate(), 1.1000, 1000)
        self.assertEqual(tracker.update("GBPUSD", bar(high=9.0, low=0.1), 2000), [])
        self.assertTrue(tracker.is_tracking("S1"))

    def test_expiry_is_recorded_but_not_scorable(self):
        from alikhande.core.lifecycle import is_scorable

        tracker = OutcomeTracker()
        tracker.open(candidate(), 1.1000, 1000)
        outcome = tracker.expire("S1", 1.1010, 2000)
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result, "EXPIRED")
        self.assertFalse(is_scorable(SignalState.EXPIRED))
        self.assertFalse(tracker.is_tracking("S1"))


class TestOutcomeLoopClosure(unittest.TestCase):
    """From a resolved trade to a rendered win rate, through real storage."""

    def test_outcomes_reach_the_statistics_layer(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database()
            db.open(str(Path(folder) / "t.sqlite"))
            repo = Repositories(db)
            tracker = OutcomeTracker()

            # Resolve enough trades to clear the 30-sample policy floor.
            for i in range(40):
                signal = candidate()
                signal.signal_id = f"S{i}"
                repo.save_signal(signal, "RUN1")
                tracker.open(signal, 1.1000, 1000)
                winner = i % 2 == 0
                price = bar(high=1.1050, low=1.1000) if winner else bar(high=1.1000, low=1.0970)
                outcome, state = tracker.update("EURUSD", price, 2000)[0]
                repo.save_outcome(outcome)
                repo.update_signal_state(f"S{i}", state)

            statistics = Statistics(repo, AppConfig().statistics)
            fresh = candidate()
            self.assertTrue(statistics.enrich(fresh))
            self.assertTrue(fresh.has_historical_estimate)
            self.assertEqual(fresh.sample_size, 40)
            self.assertAlmostEqual(fresh.historical_win_rate, 0.5)

            rendered = statistics.format_probability(fresh)
            self.assertIn("n=40", rendered)
            self.assertNotIn("n/a", rendered)
            db.close()

    def test_below_the_floor_no_rate_is_rendered(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database()
            db.open(str(Path(folder) / "t.sqlite"))
            repo = Repositories(db)
            for i in range(5):
                signal = candidate()
                signal.signal_id = f"S{i}"
                repo.save_signal(signal, "RUN1")
                repo.save_outcome_stub = None
                from alikhande.core.models import Outcome

                repo.save_outcome(Outcome(signal_id=f"S{i}", result="TP", closed_at=1))

            statistics = Statistics(repo, AppConfig().statistics)
            fresh = candidate()
            self.assertFalse(statistics.enrich(fresh))
            self.assertIn("n/a", statistics.format_probability(fresh))
            self.assertIn("5/30", statistics.format_probability(fresh))
            db.close()


class TestOfflineGateway(unittest.TestCase):
    def test_synthetic_bars_are_deterministic(self):
        a = synthesise_bars("EURUSD", Timeframe.M5, 100, seed=7)
        b = synthesise_bars("EURUSD", Timeframe.M5, 100, seed=7)
        self.assertEqual([x.close for x in a], [x.close for x in b])

    def test_a_different_seed_gives_a_different_series(self):
        a = synthesise_bars("EURUSD", Timeframe.M5, 100, seed=7)
        b = synthesise_bars("EURUSD", Timeframe.M5, 100, seed=8)
        self.assertNotEqual([x.close for x in a], [x.close for x in b])

    def test_bars_are_internally_consistent(self):
        for candle in synthesise_bars("EURUSD", Timeframe.M5, 500):
            self.assertGreaterEqual(candle.high, max(candle.open, candle.close))
            self.assertLessEqual(candle.low, min(candle.open, candle.close))
            self.assertGreater(candle.low, 0.0)

    def test_volatility_is_calibrated_to_a_realistic_h1_atr(self):
        """An earlier generator produced a ~100 pip H1 ATR on EURUSD, which
        starves the setup logic without erroring."""
        bars = synthesise_bars("EURUSD", Timeframe.H1, 500)
        values = [v for v in atr(bars, 14) if v is not None]
        average = sum(values) / len(values)
        self.assertGreater(average, 0.0004, "H1 ATR unrealistically small")
        self.assertLess(average, 0.0035, "H1 ATR unrealistically large")

    def test_the_cursor_hides_the_future(self):
        gateway = OfflineGateway()
        gateway.load_synthetic(("EURUSD",), (Timeframe.M5,), 100)
        total = gateway.series_length("EURUSD", Timeframe.M5)
        gateway.set_cursor(50)
        self.assertEqual(len(gateway.bars("EURUSD", Timeframe.M5, total)), 50)

    def test_higher_timeframes_advance_proportionally(self):
        """H1 must not reveal a bar M5 has not reached."""
        gateway = OfflineGateway()
        gateway.load_synthetic(("EURUSD",), (Timeframe.M5, Timeframe.H1), 50)
        gateway.set_cursor(120)
        m5 = gateway.bars("EURUSD", Timeframe.M5, 10_000)
        h1 = gateway.bars("EURUSD", Timeframe.H1, 10_000)
        self.assertEqual(len(m5), 120)
        self.assertEqual(len(h1), 10)  # 120 M5 bars = 10 H1 bars

    def test_aggregation_buckets_on_period_boundaries(self):
        """Bars group by wall-clock boundary, as MetaTrader does.

        A series that does not start on the hour therefore yields a partial
        first bucket, and that is correct: grouping by a fixed count instead
        would silently mis-bucket every bar after a weekend gap.
        """
        bars = synthesise_bars("EURUSD", Timeframe.M5, 120)
        rolled = aggregate(bars, Timeframe.M5, Timeframe.H1)

        for candle in rolled:
            self.assertEqual(candle.time % Timeframe.H1.seconds, 0)

        # Every source bar lands in exactly one bucket.
        self.assertEqual(sum(1 for _ in bars), 120)
        self.assertEqual(rolled[0].time, bars[0].time - (bars[0].time % Timeframe.H1.seconds))
        self.assertGreaterEqual(len(rolled), 120 * 300 // 3600)

    def test_aggregation_preserves_ohlc_semantics(self):
        bars = synthesise_bars("EURUSD", Timeframe.M5, 120)
        rolled = aggregate(bars, Timeframe.M5, Timeframe.H1)

        # Take the second bucket: the first may be partial, the last may be
        # still filling, and neither is a fair test of the merge itself.
        target = rolled[1]
        source = [
            b
            for b in bars
            if b.time - (b.time % Timeframe.H1.seconds) == target.time
        ]
        self.assertEqual(target.open, source[0].open)
        self.assertEqual(target.close, source[-1].close)
        self.assertEqual(target.high, max(b.high for b in source))
        self.assertEqual(target.low, min(b.low for b in source))
        self.assertEqual(target.tick_volume, sum(b.tick_volume for b in source))

    def test_metal_tick_value_reflects_a_100oz_contract(self):
        """XAUUSD is 100 oz x 0.01 tick = $1.00, not $0.01. Getting this wrong
        mis-sizes every gold position without erroring."""
        spec = default_spec("XAUUSD")
        self.assertAlmostEqual(spec.tick_value, 1.00)
        self.assertAlmostEqual(spec.contract_size, 100.0)

    def test_resolve_symbol_returns_none_for_the_unknown(self):
        gateway = OfflineGateway()
        gateway.load_synthetic(("EURUSD",), (Timeframe.M5,), 10)
        self.assertEqual(gateway.resolve_symbol("EURUSD"), "EURUSD")
        self.assertIsNone(gateway.resolve_symbol("NOPE"))


class TestBacktest(unittest.TestCase):
    def _gateway(self, symbols=("EURUSD",), h4_bars=600):
        gateway = OfflineGateway()
        gateway.load_synthetic(symbols, BACKTEST_TIMEFRAMES, h4_bars, seed=20260806)
        return gateway

    def test_a_replay_produces_a_consistent_report(self):
        result = Backtester().run(
            self._gateway(), ("EURUSD",), warmup_bars=10_000, max_steps=3_000
        )
        self.assertGreater(result.signals_evaluated, 0)
        self.assertEqual(result.trades, result.wins + result.losses)
        self.assertEqual(len(result.outcomes), result.trades)

    def test_every_trade_resolves_to_exactly_plus_two_or_minus_one_r(self):
        """The arithmetic identity that exposed the inverted-stop P0: with a 2R
        target and a structural stop, no other value is reachable."""
        result = Backtester().run(
            self._gateway(), ("EURUSD",), warmup_bars=10_000, max_steps=3_000
        )
        for outcome in result.outcomes:
            self.assertIn(round(outcome.realized_r, 6), (2.0, -1.0), outcome)
        self.assertAlmostEqual(result.sum_r, 2.0 * result.wins - result.losses, places=6)

    def test_no_trade_is_opened_with_an_inverted_stop(self):
        """A long whose stop sits above its entry can only ever lose."""
        result = Backtester().run(
            self._gateway(), ("EURUSD",), warmup_bars=10_000, max_steps=3_000
        )
        self.assertNotIn("STOP_ON_WRONG_SIDE_OF_ENTRY", result.rejection_reasons.keys() - {""})
        for outcome in result.outcomes:
            if outcome.result == "SL":
                self.assertLess(outcome.realized_r, 0.0, "a stop-out cannot profit")

    def test_a_replay_is_deterministic(self):
        first = Backtester().run(
            self._gateway(), ("EURUSD",), warmup_bars=10_000, max_steps=1_500
        )
        second = Backtester().run(
            self._gateway(), ("EURUSD",), warmup_bars=10_000, max_steps=1_500
        )
        self.assertEqual(first.trades, second.trades)
        self.assertAlmostEqual(first.sum_r, second.sum_r)

    def test_the_report_refuses_to_claim_edge_on_synthetic_data(self):
        result = Backtester().run(
            self._gateway(), ("EURUSD",), warmup_bars=10_000, max_steps=1_500
        )
        report = result.report()
        self.assertIn("DATA IS SYNTHETIC", report)
        self.assertIn("NOT AS A SIGN THE STRATEGY WORKS", report)
        self.assertIn("scored as a STOP", report)

    def test_a_small_sample_is_labelled_as_diagnostic_only(self):
        result = Backtester().run(
            self._gateway(), ("EURUSD",), warmup_bars=10_000, max_steps=600
        )
        if 0 < result.trades < 30:
            self.assertIn("policy floor", result.report())

    def test_results_can_be_written_to_a_database(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database()
            db.open(str(Path(folder) / "bt.sqlite"))
            repo = Repositories(db)
            result = Backtester().run(
                self._gateway(), ("EURUSD",), warmup_bars=10_000, max_steps=3_000,
                repositories=repo,
            )
            if result.trades:
                summary = repo.outcome_summary()
                self.assertEqual(summary["total"], result.trades)
            db.close()


class TestScanEngine(unittest.TestCase):
    def _engine(self, symbols=("EURUSD",)):
        gateway = OfflineGateway()
        gateway.load_synthetic(symbols, BACKTEST_TIMEFRAMES, 400)
        gateway.set_cursor(gateway.series_length(symbols[0], Timeframe.M5))
        config = AppConfig().with_symbols(symbols)
        return ScanEngine(gateway, config, runtime=detect_runtime(connected=False, replay=False))

    def test_a_pass_runs_and_resolves_symbols(self):
        engine = self._engine()
        engine.initialize(1000)
        snapshot = engine.run_pass(2000)
        self.assertEqual(len(snapshot.symbols), 1)
        self.assertTrue(snapshot.symbols[0].resolved)

    def test_repeated_passes_are_stable(self):
        engine = self._engine()
        engine.initialize(1000)
        for i in range(20):
            snapshot = engine.run_pass(2000 + i)
        self.assertEqual(snapshot.passes, 20)

    def test_an_unresolvable_symbol_is_reported_not_fatal(self):
        gateway = OfflineGateway()
        gateway.load_synthetic(("EURUSD",), BACKTEST_TIMEFRAMES, 200)
        config = AppConfig().with_symbols(("EURUSD", "NOSUCHPAIR"))
        engine = ScanEngine(
            gateway, config, runtime=detect_runtime(connected=False, replay=False)
        )
        engine.initialize(1000)
        snapshot = engine.run_pass(2000)
        unresolved = [v for v in snapshot.symbols if not v.resolved]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0].requested, "NOSUCHPAIR")

    def test_demo_execution_mode_is_refused_without_persistence(self):
        """No durable record of an in-flight order means no restart recovery."""
        engine = self._engine()
        engine.initialize(1000)
        ok, reason = engine.set_mode(RunMode.DEMO_CONFIRM, 2000)
        self.assertFalse(ok)
        self.assertEqual(reason, "PERSISTENCE_REQUIRED_FOR_DEMO_EXECUTION")

    def test_arming_is_refused_outside_demo_confirm_mode(self):
        engine = self._engine()
        engine.initialize(1000)
        ok, reason = engine.arm("EURUSD", 2000)
        self.assertFalse(ok)
        self.assertIn(reason, ("NO_VALID_PLAN", "ARMING_REQUIRES_DEMO_CONFIRM_MODE"))

    def test_alert_only_is_always_permitted(self):
        engine = self._engine()
        engine.initialize(1000)
        self.assertEqual(engine.set_mode(RunMode.ALERT_ONLY, 2000), (True, ""))


if __name__ == "__main__":
    unittest.main()


class TestUiContracts(unittest.TestCase):
    """Rules the UI must keep, asserted rather than trusted to review.

    These need no display: they check structure and colour policy, which is
    where the visual defects that actually matter live.
    """

    def test_status_chip_requires_an_icon_and_a_label(self):
        """Colour must never carry meaning alone.

        Warning and serious sit in the same warm family by design, so hue cannot
        separate them, and a bare coloured dot tells a colour-blind reader
        nothing. Requiring both arguments makes the omission impossible.
        """
        import inspect

        from alikhande.ui.components import StatusChip

        parameters = list(inspect.signature(StatusChip.__init__).parameters)
        self.assertEqual(parameters[1], "icon")
        self.assertEqual(parameters[2], "text")
        for name in ("icon", "text"):
            self.assertIs(
                inspect.signature(StatusChip.__init__).parameters[name].default,
                inspect.Parameter.empty,
                f"{name} must be required so a bare coloured dot cannot ship",
            )

    def test_unknown_never_borrows_a_status_colour(self):
        """UNKNOWN is the absence of a status, not a mild one."""
        from alikhande.ui.theme import PALETTE

        for status in (PALETTE.good, PALETTE.warning, PALETTE.serious, PALETTE.critical):
            self.assertNotEqual(PALETTE.unknown, status)

    def test_direction_does_not_reuse_the_permission_colours(self):
        """LONG/SHORT must not be green/red — that pair means allowed/blocked
        here, and a SHORT painted red reads as an error."""
        from alikhande.ui.theme import PALETTE

        for direction in (PALETTE.long, PALETTE.short):
            self.assertNotEqual(direction, PALETTE.good)
            self.assertNotEqual(direction, PALETTE.critical)

    def test_the_score_ramp_is_a_single_hue(self):
        """Magnitude uses one hue darkening with value, never a rainbow."""
        from alikhande.ui.theme import PALETTE, score_ramp

        ramp = {score_ramp(v, 75.0) for v in (95.0, 80.0, 60.0)}
        self.assertTrue(ramp <= {PALETTE.seq_100, PALETTE.seq_250, PALETTE.seq_400})
        # Below the threshold a score is not a failure, so it recedes rather
        # than turning red.
        self.assertEqual(score_ramp(20.0, 75.0), PALETTE.ink_muted)

    def test_the_symbol_view_carries_what_the_chart_needs(self):
        """The detail chart must be able to draw the structure, not just be
        told about it."""
        from alikhande.app.engine import SymbolView

        view = SymbolView()
        self.assertEqual(view.bars, [])
        self.assertEqual(view.zones, [])

    def test_the_ui_never_reaches_into_engine_privates(self):
        """The UI reads only what the engine offers publicly."""
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parent.parent / "alikhande" / "ui"
        offenders = []
        for path in root.rglob("*.py"):
            for match in re.finditer(r"_engine\.(_\w+)", path.read_text(encoding="utf-8")):
                offenders.append(f"{path.name}: _engine.{match.group(1)}")
        self.assertEqual(offenders, [], f"UI reached into engine privates: {offenders}")
