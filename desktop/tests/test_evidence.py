"""The evidence layer, the scanner ranking and the presets.

These are the tests that matter most in this change, because the thing being
built is a screen that shows percentages, and a percentage on a trading screen
is believed. Most of what follows checks that a number is *withheld* rather
than that it is computed — the arithmetic is the easy half.
"""

from __future__ import annotations

import unittest

from alikhande.app import scanner as scanner_app
from alikhande.app.engine import EngineSnapshot, SymbolView
from alikhande.config import AppConfig
from alikhande.core.enums import Direction, SetupType
from alikhande.core.evidence import (
    PROVISIONAL_SAMPLE,
    EvidenceTier,
    Provenance,
    assess,
    breakeven_win_rate,
    expectancy_r,
    provenance_of,
)
from alikhande.core.models import SignalCandidate, SymbolSnapshot, TradePlan
from alikhande.profiles import (
    AUTO_MINIMUM_SAMPLE,
    Overrides,
    Profile,
    auto_overrides,
    clamp,
    configure,
)


def evidence(wins: int, total: int, rr: float = 2.0, score: float = 80.0, **kwargs):
    return assess(
        wins=wins,
        total=total,
        reward_risk=rr,
        rule_score=score,
        score_threshold=75.0,
        **kwargs,
    )


class TestArithmetic(unittest.TestCase):
    def test_break_even_is_the_rate_at_which_expectancy_is_zero(self):
        for reward_risk in (0.5, 1.0, 2.0, 3.5, 10.0):
            rate = breakeven_win_rate(reward_risk)
            self.assertAlmostEqual(expectancy_r(rate, reward_risk), 0.0, places=9)

    def test_a_reward_of_zero_needs_a_certainty_it_cannot_have(self):
        """Rather than dividing by zero or reporting a reachable rate."""
        self.assertEqual(breakeven_win_rate(0.0), 1.0)
        self.assertEqual(breakeven_win_rate(-3.0), 1.0)

    def test_expectancy_uses_a_full_r_for_the_loss_case(self):
        # 60% at 2R: 0.6*2 - 0.4 = 0.8
        self.assertAlmostEqual(expectancy_r(0.6, 2.0), 0.8)


class TestTiers(unittest.TestCase):
    def test_nothing_is_claimed_below_the_provisional_floor(self):
        result = evidence(wins=5, total=PROVISIONAL_SAMPLE - 1)
        self.assertEqual(result.tier, EvidenceTier.UNMEASURED)
        self.assertFalse(result.has_rate)

    def test_a_thin_sample_is_provisional_and_still_shows_no_headline(self):
        result = evidence(wins=6, total=9)
        self.assertEqual(result.tier, EvidenceTier.PROVISIONAL)
        self.assertFalse(
            result.has_rate,
            "a headline percentage over nine trades is a lie told with true numbers",
        )

    def test_the_floor_is_the_configured_minimum_not_a_literal(self):
        self.assertEqual(evidence(20, 30).tier, EvidenceTier.MEASURED)
        self.assertEqual(
            assess(
                wins=20,
                total=30,
                reward_risk=2.0,
                rule_score=80.0,
                score_threshold=75.0,
                min_sample=100,
            ).tier,
            EvidenceTier.PROVISIONAL,
        )

    def test_an_empty_sample_claims_nothing_and_carries_no_provenance(self):
        result = evidence(0, 0, provenance=Provenance.LIVE)
        self.assertEqual(result.tier, EvidenceTier.UNMEASURED)
        self.assertEqual(result.provenance, Provenance.NONE)
        self.assertEqual(result.low, 0.0)

    def test_impossible_counts_are_refused_rather_than_normalised(self):
        """More wins than trades is corrupt input, not a 100% win rate."""
        result = evidence(40, 30)
        self.assertEqual(result.tier, EvidenceTier.UNMEASURED)
        self.assertEqual(result.point, 0.0)


class TestConservativeBound(unittest.TestCase):
    def test_the_lower_bound_is_below_the_point_estimate(self):
        result = evidence(30, 50)
        self.assertLess(result.low, result.point)
        self.assertGreater(result.high, result.point)

    def test_a_larger_sample_at_the_same_rate_gives_a_tighter_bound(self):
        """This is the property that makes the bound worth ranking on."""
        small = evidence(18, 30)
        large = evidence(120, 200)
        self.assertAlmostEqual(small.point, large.point, places=6)
        self.assertGreater(
            large.low,
            small.low,
            "the better-established sample must rank above the thinner one",
        )

    def test_clearing_break_even_is_judged_on_the_bound_not_the_point(self):
        # 40 wins in 100 at RR 1.0: point 0.40 clears nothing; break-even is
        # 0.50, so this must be false on either reading.
        self.assertFalse(evidence(40, 100, rr=1.0).clears_breakeven)

        # 55 in 100 at RR 1.0: the point estimate clears 0.50, the Wilson lower
        # bound (~0.45) does not. The conservative reading is the one that
        # decides.
        marginal = evidence(55, 100, rr=1.0)
        self.assertGreater(marginal.point, marginal.breakeven)
        self.assertLess(marginal.low, marginal.breakeven)
        self.assertFalse(marginal.clears_breakeven)

    def test_an_unmeasured_setup_never_clears_break_even(self):
        """However high its rule score."""
        result = evidence(0, 0, score=99.0)
        self.assertFalse(result.clears_breakeven)


class TestProvenance(unittest.TestCase):
    def test_live_and_replay_together_are_mixed_not_live(self):
        self.assertEqual(provenance_of({"LIVE", "REPLAY"}), Provenance.MIXED)

    def test_each_source_alone_reports_itself(self):
        self.assertEqual(provenance_of({"LIVE"}), Provenance.LIVE)
        self.assertEqual(provenance_of({"REPLAY"}), Provenance.REPLAY)
        self.assertEqual(provenance_of({"OFFLINE"}), Provenance.REPLAY)

    def test_an_unrecognised_kind_is_not_guessed_at(self):
        self.assertEqual(provenance_of({"SOMETHING_ELSE"}), Provenance.NONE)
        self.assertEqual(provenance_of(set()), Provenance.NONE)


class TestRanking(unittest.TestCase):
    def test_measured_outranks_a_high_unmeasured_score(self):
        measured = evidence(20, 40, score=60.0)
        guessed = evidence(0, 0, score=99.0)
        self.assertGreater(measured.rank_key, guessed.rank_key)

    def test_within_a_tier_conservative_expectancy_decides(self):
        better = evidence(140, 200)
        worse = evidence(100, 200)
        self.assertGreater(better.rank_key, worse.rank_key)


class TestScannerRanking(unittest.TestCase):
    def _view(self, symbol: str, *, valid: bool, score: float = 80.0) -> SymbolView:
        signal = SignalCandidate(
            signal_id=f"sig-{symbol}",
            symbol=symbol,
            direction=Direction.LONG,
            setup=SetupType.TREND_PULLBACK,
            preferred_entry=1.1000,
            stop_loss=1.0950,
            take_profit=1.1150,
            long_score=score,
            rule_version="test",
        )
        plan = TradePlan(
            symbol=symbol,
            direction=Direction.LONG,
            entry=1.1000,
            stop_loss=1.0950,
            take_profit=1.1150,
            valid=valid,
            validation_codes=[] if valid else ["RR_BELOW_MINIMUM"],
        )
        return SymbolView(
            requested=symbol,
            symbol=symbol,
            resolved=True,
            snapshot=SymbolSnapshot(symbol=symbol, digits=5),
            signal=signal,
            plan=plan,
        )

    def test_a_blocked_setup_never_outranks_a_tradable_one(self):
        snapshot = EngineSnapshot(
            symbols=[
                self._view("BLOCKED", valid=False, score=99.0),
                self._view("TRADABLE", valid=True, score=51.0),
            ]
        )
        ranked = scanner_app.build(snapshot, AppConfig())
        self.assertEqual(ranked[0].symbol, "TRADABLE")
        self.assertFalse(ranked[1].tradable)
        self.assertEqual(ranked[1].blocked_reason, "RR_BELOW_MINIMUM")

    def test_every_symbol_appears_including_the_empty_ones(self):
        """A scanner that hides its misses teaches you it always finds
        something."""
        snapshot = EngineSnapshot(
            symbols=[
                self._view("EURUSD", valid=True),
                SymbolView(requested="GBPUSD", symbol="GBPUSD", resolved=True),
            ]
        )
        ranked = scanner_app.build(snapshot, AppConfig())
        self.assertEqual({o.symbol for o in ranked}, {"EURUSD", "GBPUSD"})

    def test_reward_risk_comes_out_of_the_plan_geometry(self):
        snapshot = EngineSnapshot(symbols=[self._view("EURUSD", valid=True)])
        ranked = scanner_app.build(snapshot, AppConfig())
        # risk 50 points, reward 150 points
        self.assertAlmostEqual(ranked[0].reward_risk, 3.0, places=6)

    def test_a_degenerate_stop_reports_no_rr_rather_than_zero(self):
        view = self._view("EURUSD", valid=True)
        view.plan.stop_loss = view.plan.entry
        ranked = scanner_app.build(EngineSnapshot(symbols=[view]), AppConfig())
        self.assertEqual(ranked[0].reward_risk, 0.0)

    def test_actionable_excludes_tradable_but_unevidenced(self):
        snapshot = EngineSnapshot(symbols=[self._view("EURUSD", valid=True)])
        ranked = scanner_app.build(snapshot, AppConfig())
        self.assertTrue(ranked[0].tradable)
        self.assertEqual(
            scanner_app.actionable(ranked),
            [],
            "the badge must count evidence, not merely a passed gate",
        )

    def test_ranking_survives_a_repository_without_the_provenance_method(self):
        """Offline sessions and older databases hand over a narrower object."""

        class Narrow:
            pass

        snapshot = EngineSnapshot(symbols=[self._view("EURUSD", valid=True)])
        ranked = scanner_app.build(snapshot, AppConfig(), Narrow())
        self.assertEqual(ranked[0].evidence.tier, EvidenceTier.UNMEASURED)


class TestPresets(unittest.TestCase):
    def test_the_policy_floors_cannot_be_dialled_down(self):
        loosened = Overrides(
            score_threshold=5.0,
            minimum_risk_reward=0.5,
            risk_percent=99.0,
            min_outcome_sample=3,
        )
        result = clamp(loosened)
        self.assertGreaterEqual(result.score_threshold, 50.0)
        self.assertGreaterEqual(result.minimum_risk_reward, 2.0)
        self.assertLessEqual(result.risk_percent, AppConfig().risk.maximum_risk_percent)
        self.assertGreaterEqual(result.min_outcome_sample, 30)

    def test_raising_a_floor_is_allowed(self):
        result = clamp(Overrides(minimum_risk_reward=4.0, min_outcome_sample=120))
        self.assertEqual(result.minimum_risk_reward, 4.0)
        self.assertEqual(result.min_outcome_sample, 120)

    def test_auto_does_nothing_without_enough_evidence(self):
        base = Overrides()
        self.assertEqual(auto_overrides(None), base)
        self.assertEqual(auto_overrides({"total": 10, "avg_r": -1.0}), base)

    def test_auto_tightens_when_the_measured_record_is_negative(self):
        result = auto_overrides({"total": AUTO_MINIMUM_SAMPLE, "avg_r": -0.3})
        self.assertGreater(result.score_threshold, Overrides().score_threshold)
        self.assertGreaterEqual(result.minimum_risk_reward, 2.5)

    def test_auto_can_never_loosen(self):
        """The property that stops an adaptive system relaxing itself to zero
        after a good run."""
        base = Overrides()
        for average in (-2.0, -0.5, 0.0, 0.05, 0.2, 5.0):
            result = auto_overrides({"total": 500, "avg_r": average})
            self.assertGreaterEqual(result.score_threshold, base.score_threshold)
            self.assertGreaterEqual(
                result.minimum_risk_reward, base.minimum_risk_reward
            )
            self.assertLessEqual(result.risk_percent, base.risk_percent)

    def test_configure_keeps_the_symbols_it_was_given(self):
        base = AppConfig().with_symbols(("XAUUSD",))
        result = configure(base, Profile.AUTO, summary={"total": 500, "avg_r": -1.0})
        self.assertEqual(result.symbols, ("XAUUSD",))
        self.assertGreater(
            result.scoring.score_threshold, base.scoring.score_threshold
        )

    def test_an_unparseable_preset_name_falls_back_to_default(self):
        self.assertIs(Profile.parse("nonsense"), Profile.DEFAULT)
        self.assertIs(Profile.parse(None), Profile.DEFAULT)
        self.assertIs(Profile.parse("AUTO"), Profile.AUTO)

    def test_a_corrupt_overrides_blob_does_not_stop_the_app(self):
        result = Overrides.from_dict({"score_threshold": "not a number"})
        self.assertEqual(result.score_threshold, Overrides().score_threshold)
        self.assertEqual(Overrides.from_dict(None), Overrides())


if __name__ == "__main__":
    unittest.main()
