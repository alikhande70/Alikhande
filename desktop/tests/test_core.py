"""Tests for the pure core: hashing, indicators, analysis, statistics, lifecycle.

These are the tests the MQL5 build could never have. Every assertion here is a
claim that has actually been executed, not one that has been reasoned about.
"""

from __future__ import annotations

import math
import unittest

from alikhande.config import AppConfig
from alikhande.core import indicators as ind
from alikhande.core.enums import (
    Direction,
    SetupType,
    SignalState,
    SpreadState,
    Timeframe,
    ZoneRelation,
    ZoneType,
)
from alikhande.core.hashing import fnv1a, fnv1a64
from alikhande.core.lifecycle import is_scorable, is_terminal, transition_allowed
from alikhande.core.models import Bar, SignalCandidate, SymbolSnapshot, Zone
from alikhande.core.spread import SpreadTracker
from alikhande.core.statistics import Statistics, wilson
from alikhande.core.trend import TrendEngine, directional_bonus
from alikhande.core.zones import (
    ZoneEngine,
    find_nearest_zone,
    find_zone_beyond,
    zone_anchors,
    zone_relation,
)


def ramp(count: int, start: float = 1.1000, step: float = 0.0002, spread: float = 0.0004):
    """A clean monotonic series — deterministic and easy to reason about."""
    bars = []
    price = start
    for i in range(count):
        bars.append(
            Bar(
                time=i * 3600,
                open=price,
                high=price + spread,
                low=price - spread,
                close=price,
            )
        )
        price += step
    return bars


class TestHashing(unittest.TestCase):
    def test_matches_canonical_fnv_vectors(self):
        # The published FNV-1a reference values. Getting these right is what
        # makes a signal id computed here agree with one computed by the EA.
        self.assertEqual(fnv1a64("test").lower(), "f9e6e6ef197c2b25")
        self.assertEqual(fnv1a("a"), "E40C292C")

    def test_is_deterministic_and_sensitive(self):
        self.assertEqual(fnv1a("EURUSD|1|1|1700000000"), fnv1a("EURUSD|1|1|1700000000"))
        self.assertNotEqual(fnv1a("EURUSD|1|1|1700000000"), fnv1a("EURUSD|1|1|1700000001"))

    def test_handles_non_ascii(self):
        self.assertEqual(len(fnv1a64("طلا")), 16)


class TestIndicators(unittest.TestCase):
    def test_ema_seeds_from_first_value(self):
        series = ind.ema([10.0, 10.0, 10.0, 10.0], 3)
        self.assertEqual(series[0], 10.0)
        for value in series:
            self.assertAlmostEqual(value, 10.0)

    def test_ema_converges_upward_on_a_rising_series(self):
        values = [float(i) for i in range(1, 60)]
        series = ind.ema(values, 10)
        self.assertLess(series[-1], values[-1])  # lags
        self.assertGreater(series[-1], series[-10])  # but rises

    def test_atr_is_a_simple_average_of_true_range(self):
        """MT5's ATR is an SMA of TR, not Wilder smoothing. This pins that."""
        bars = ramp(60)
        atr = ind.atr(bars, 14)
        tr = ind.true_range(bars)
        expected = sum(tr[-14:]) / 14
        self.assertAlmostEqual(atr[-1], expected, places=12)

    def test_atr_first_defined_index_accounts_for_undefined_first_tr(self):
        atr = ind.atr(ramp(60), 14)
        self.assertIsNone(atr[13])
        self.assertIsNotNone(atr[14])

    def test_atr_returns_all_none_when_history_is_too_short(self):
        self.assertTrue(all(v is None for v in ind.atr(ramp(10), 14)))

    def test_adx_stays_in_range_and_warms_up_late(self):
        bars = ramp(120)
        adx = ind.adx(bars, 14)
        defined = [v for v in adx if v is not None]
        self.assertTrue(defined)
        self.assertTrue(all(0.0 <= v <= 100.0 for v in defined))
        # Wilder ADX needs roughly two periods before its first value.
        first = next(i for i, v in enumerate(adx) if v is not None)
        self.assertGreaterEqual(first, 14 * 2 - 2)

    def test_adx_is_high_on_a_pure_trend(self):
        adx = ind.adx(ramp(200), 14)
        self.assertGreater([v for v in adx if v is not None][-1], 60.0)

    def test_median_matches_the_mql5_even_length_rule(self):
        self.assertEqual(ind.median([3.0, 1.0, 2.0]), 2.0)
        self.assertEqual(ind.median([4.0, 1.0, 3.0, 2.0]), 2.5)
        self.assertEqual(ind.median([]), 0.0)

    def test_last_defined_refuses_a_partially_warmed_series(self):
        self.assertIsNone(ind.last_defined([None, None, 1.0], 2))
        self.assertEqual(ind.last_defined([None, 1.0, 2.0], 2), [1.0, 2.0])


class TestTrend(unittest.TestCase):
    def setUp(self):
        self.engine = TrendEngine()

    def test_refuses_when_history_is_insufficient(self):
        self.assertFalse(self.engine.analyze(ramp(50), Timeframe.H1, 0.00001).valid)

    def test_refuses_when_point_is_zero(self):
        self.assertFalse(self.engine.analyze(ramp(400), Timeframe.H1, 0.0).valid)

    def test_scores_a_rising_series_bullish(self):
        result = self.engine.analyze(ramp(400), Timeframe.H1, 0.00001)
        self.assertTrue(result.valid)
        self.assertGreater(result.direction_score, 0.0)
        self.assertGreater(result.ema_fast, result.ema_slow)

    def test_scores_a_falling_series_bearish(self):
        result = self.engine.analyze(ramp(400, 1.3000, -0.0002), Timeframe.H1, 0.00001)
        self.assertTrue(result.valid)
        self.assertLess(result.direction_score, 0.0)

    def test_drops_the_forming_bar(self):
        """The last bar is still moving; acting on it is look-ahead."""
        bars = ramp(400)
        rigged = list(bars)
        rigged[-1] = Bar(time=rigged[-1].time, open=9.0, high=9.0, low=9.0, close=9.0)
        self.assertEqual(
            self.engine.analyze(bars, Timeframe.H1, 0.00001).direction_score,
            self.engine.analyze(rigged, Timeframe.H1, 0.00001).direction_score,
        )

    def test_available_information_time_is_the_bar_close(self):
        bars = ramp(400)
        result = self.engine.analyze(bars, Timeframe.H1, 0.00001)
        self.assertEqual(result.available_information_time, bars[-2].time + 3600)

    def test_strength_is_a_magnitude(self):
        result = self.engine.analyze(ramp(400, 1.3000, -0.0002), Timeframe.H1, 0.00001)
        self.assertGreaterEqual(result.strength, 0.0)

    def test_directional_bonus_never_rewards_the_opposing_side(self):
        """The two-sided strength bug: a bearish trend must not feed longs."""
        bearish = self.engine.analyze(ramp(400, 1.3000, -0.0002), Timeframe.H1, 0.00001)
        self.assertEqual(directional_bonus(bearish, Direction.LONG), 0.0)
        self.assertGreater(directional_bonus(bearish, Direction.SHORT), 0.0)

    def test_directional_bonus_is_zero_for_an_invalid_trend(self):
        from alikhande.core.models import TrendResult

        self.assertEqual(directional_bonus(TrendResult(), Direction.LONG), 0.0)


class TestZones(unittest.TestCase):
    def test_relation_reports_unavailable_for_an_unusable_zone(self):
        self.assertEqual(zone_relation(Zone(), 1.0), ZoneRelation.UNAVAILABLE)
        broken = Zone(low=1.0, high=2.0, valid=True, broken=True)
        self.assertEqual(zone_relation(broken, 1.5), ZoneRelation.UNAVAILABLE)

    def test_relation_distinguishes_all_three_positions(self):
        zone = Zone(low=1.0, high=2.0, center=1.5, valid=True)
        self.assertEqual(zone_relation(zone, 0.5), ZoneRelation.BELOW)
        self.assertEqual(zone_relation(zone, 1.5), ZoneRelation.INSIDE)
        self.assertEqual(zone_relation(zone, 2.5), ZoneRelation.ABOVE)

    def test_anchoring_respects_zone_type(self):
        demand = Zone(type=ZoneType.DEMAND, valid=True)
        supply = Zone(type=ZoneType.SUPPLY, valid=True)
        self.assertTrue(zone_anchors(demand, Direction.LONG))
        self.assertFalse(zone_anchors(demand, Direction.SHORT))
        self.assertTrue(zone_anchors(supply, Direction.SHORT))
        self.assertFalse(zone_anchors(supply, Direction.LONG))
        self.assertFalse(zone_anchors(demand, Direction.NONE))

    def test_nearest_zone_finds_a_zone_price_is_inside(self):
        """v1.1.0's search excluded exactly this case — the pullback moment."""
        zones = [Zone(type=ZoneType.DEMAND, low=1.0, high=2.0, center=1.5, valid=True)]
        self.assertEqual(find_nearest_zone(zones, ZoneType.DEMAND, 1.5, 5.0), 0)

    def test_nearest_zone_respects_the_distance_limit(self):
        zones = [Zone(type=ZoneType.DEMAND, low=1.0, high=2.0, center=1.5, valid=True)]
        self.assertEqual(find_nearest_zone(zones, ZoneType.DEMAND, 99.0, 1.0), -1)

    def test_nearest_zone_ignores_the_wrong_type(self):
        zones = [Zone(type=ZoneType.SUPPLY, low=1.0, high=2.0, center=1.5, valid=True)]
        self.assertEqual(find_nearest_zone(zones, ZoneType.DEMAND, 1.5, 5.0), -1)

    def test_find_zone_beyond_respects_direction(self):
        zones = [
            Zone(type=ZoneType.SUPPLY, low=2.0, high=3.0, center=2.5, valid=True),
            Zone(type=ZoneType.SUPPLY, low=0.1, high=0.2, center=0.15, valid=True),
        ]
        self.assertEqual(find_zone_beyond(zones, ZoneType.SUPPLY, 1.0, True), 0)
        self.assertEqual(find_zone_beyond(zones, ZoneType.SUPPLY, 1.0, False), 1)

    def test_build_separates_supply_from_demand(self):
        """v1.1.0 merged highs and lows into one band, inflating touch counts."""
        bars = []
        price = 1.1000
        for i in range(300):
            wave = math.sin(i / 9.0) * 0.0050
            close = price + wave
            bars.append(
                Bar(
                    time=i * 3600,
                    open=close,
                    high=close + 0.0006,
                    low=close - 0.0006,
                    close=close,
                )
            )
        zones = ZoneEngine().build("EURUSD", bars, Timeframe.H1, 0.00001)
        self.assertTrue(zones)
        for zone in zones:
            self.assertIn(zone.type, (ZoneType.SUPPLY, ZoneType.DEMAND))
            self.assertLess(zone.low, zone.high)
            self.assertGreaterEqual(zone.touches, 1)

    def test_confirmation_time_is_later_than_the_pivot(self):
        bars = []
        for i in range(300):
            close = 1.1 + math.sin(i / 7.0) * 0.004
            bars.append(
                Bar(time=i * 3600, open=close, high=close + 0.0006, low=close - 0.0006, close=close)
            )
        for zone in ZoneEngine().build("EURUSD", bars, Timeframe.H1, 0.00001):
            self.assertGreater(zone.confirmation_time, zone.pivot_time)

    def test_build_refuses_a_short_series(self):
        self.assertEqual(ZoneEngine().build("EURUSD", ramp(20), Timeframe.H1, 0.00001), [])


class TestSpreadTracker(unittest.TestCase):
    def test_warms_up_before_classifying(self):
        tracker = SpreadTracker()
        tracker.add(10.0)
        state, ratio, percentile = tracker.classify(10.0)
        self.assertEqual(state, SpreadState.WARMING_UP)
        # Zeroed so an unwarmed tracker can never read as a normal spread.
        self.assertEqual(ratio, 0.0)
        self.assertEqual(percentile, 0.0)

    def test_classifies_relative_to_its_own_median(self):
        tracker = SpreadTracker()
        for _ in range(40):
            tracker.add(10.0)
        self.assertEqual(tracker.classify(10.0)[0], SpreadState.NORMAL)
        self.assertEqual(tracker.classify(15.0)[0], SpreadState.ELEVATED)
        self.assertEqual(tracker.classify(20.0)[0], SpreadState.HIGH)
        self.assertEqual(tracker.classify(100.0)[0], SpreadState.EXTREME)

    def test_ignores_non_positive_samples(self):
        tracker = SpreadTracker()
        tracker.add(0.0)
        tracker.add(-1.0)
        self.assertEqual(tracker.count, 0)

    def test_is_bounded(self):
        tracker = SpreadTracker()
        for i in range(1000):
            tracker.add(float(i + 1))
        self.assertLessEqual(tracker.count, AppConfig().scan.spread_sample_capacity)


class TestStatistics(unittest.TestCase):
    def test_wilson_matches_independently_computed_bounds(self):
        low, high = wilson(15, 30)
        self.assertAlmostEqual(low, 0.3315, places=3)
        self.assertAlmostEqual(high, 0.6685, places=3)

    def test_wilson_stays_inside_the_unit_interval_at_the_extremes(self):
        low, high = wilson(0, 10)
        self.assertGreaterEqual(low, 0.0)
        self.assertLess(high, 1.0)
        low, high = wilson(10, 10)
        self.assertGreater(low, 0.0)
        self.assertLessEqual(high, 1.0)

    def test_wilson_refuses_nonsense(self):
        self.assertIsNone(wilson(0, 0))
        self.assertIsNone(wilson(5, 3))
        self.assertIsNone(wilson(-1, 3))

    def test_enrich_withholds_below_the_sample_floor(self):
        class Counter:
            def outcome_counts(self, symbol, setup, rule_version):
                return 8, 10

        candidate = SignalCandidate(symbol="EURUSD", setup=SetupType.TREND_PULLBACK)
        statistics = Statistics(Counter())
        self.assertFalse(statistics.enrich(candidate))
        self.assertFalse(candidate.has_historical_estimate)
        self.assertEqual(candidate.sample_size, 10)
        self.assertIn("n/a", statistics.format_probability(candidate))

    def test_enrich_reports_above_the_sample_floor(self):
        class Counter:
            def outcome_counts(self, symbol, setup, rule_version):
                return 20, 40

        candidate = SignalCandidate(symbol="EURUSD", setup=SetupType.TREND_PULLBACK)
        statistics = Statistics(Counter())
        self.assertTrue(statistics.enrich(candidate))
        self.assertTrue(candidate.has_historical_estimate)
        self.assertAlmostEqual(candidate.historical_win_rate, 0.5)
        rendered = statistics.format_probability(candidate)
        # A rate never appears without its interval and sample size.
        self.assertIn("50%", rendered)
        self.assertIn("n=40", rendered)
        self.assertIn("[", rendered)

    def test_enrich_refuses_without_a_counter(self):
        candidate = SignalCandidate(symbol="EURUSD", setup=SetupType.TREND_PULLBACK)
        self.assertFalse(Statistics(None).enrich(candidate))

    def test_enrich_refuses_without_a_setup(self):
        class Counter:
            def outcome_counts(self, symbol, setup, rule_version):
                return 100, 100

        candidate = SignalCandidate(symbol="EURUSD", setup=SetupType.NONE)
        self.assertFalse(Statistics(Counter()).enrich(candidate))


class TestLifecycle(unittest.TestCase):
    def test_terminal_states_are_final(self):
        for state in (
            SignalState.TP,
            SignalState.SL,
            SignalState.EXPIRED,
            SignalState.INVALIDATED,
            SignalState.NOT_FILLED,
            SignalState.AMBIGUOUS,
        ):
            self.assertTrue(is_terminal(state))
            self.assertFalse(transition_allowed(state, SignalState.CANDIDATE))

    def test_only_tp_and_sl_are_scorable(self):
        """Expiry describes the scanner, not the setup's edge."""
        self.assertTrue(is_scorable(SignalState.TP))
        self.assertTrue(is_scorable(SignalState.SL))
        for state in (SignalState.EXPIRED, SignalState.INVALIDATED, SignalState.NOT_FILLED):
            self.assertFalse(is_scorable(state))

    def test_the_happy_path_is_permitted(self):
        path = [
            SignalState.NONE,
            SignalState.CANDIDATE,
            SignalState.CONFIRMED,
            SignalState.PREVIEWED,
            SignalState.ACTIVE,
            SignalState.TP,
        ]
        for source, target in zip(path, path[1:]):
            self.assertTrue(transition_allowed(source, target), f"{source} -> {target}")

    def test_skipping_states_is_refused(self):
        self.assertFalse(transition_allowed(SignalState.NONE, SignalState.ACTIVE))
        self.assertFalse(transition_allowed(SignalState.CANDIDATE, SignalState.TP))
        self.assertFalse(transition_allowed(SignalState.CONFIRMED, SignalState.ACTIVE))

    def test_self_transition_is_refused(self):
        self.assertFalse(transition_allowed(SignalState.ACTIVE, SignalState.ACTIVE))


if __name__ == "__main__":
    unittest.main()
