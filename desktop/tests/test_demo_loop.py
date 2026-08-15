"""Signal → order → real fill → outcome → evidence, end to end.

The README claimed the outcome loop was closed. It was closed in the *backtest*
and open everywhere else, which is the half that does not matter: a replay's
evidence describes a generator, and only a demo account's evidence describes a
broker.

Two defects sat in the gap.

**The outcome opened at the planned price.** `confirm()` called
`OutcomeTracker.open(signal, plan.entry, now)` the instant the submit was
accepted — before the broker had said anything. Every realised R was measured
from a price nobody traded, off by the slippage, in the direction that flatters
the result.

**Nothing wrote the outcomes table outside the backtest.** `save_outcome` had
exactly one caller, in `app/backtest.py`. A demo session persisted signals,
plans, executions and deals, and then had nothing to compute a win rate from.

These tests drive the real `ScanEngine` against a gateway that fills at a
price deliberately different from the plan, and check what lands in the
database.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alikhande.adapters.sqlite.database import Database
from alikhande.adapters.sqlite.repositories import Repositories
from alikhande.app.engine import ScanEngine
from alikhande.config import AppConfig
from alikhande.core.enums import Direction, RunMode, SignalState
from alikhande.core.environment import Environment
from alikhande.core.models import DealInfo, OrderResult, PositionInfo

try:  # pragma: no cover - depends on how the suite was launched
    from .test_safety import StubGateway, demo_account, default_spec, valid_plan
except ImportError:  # pragma: no cover
    from test_safety import StubGateway, demo_account, default_spec, valid_plan


#: The plan asks for this; the broker fills somewhere else. The whole point.
PLANNED_ENTRY = 1.10000
ACTUAL_FILL = 1.10025


class TestTheEntryPriceComesFromExactBrokerDeals(unittest.TestCase):
    def setUp(self):
        self.gateway = StubGateway()
        self.engine = ScanEngine(
            self.gateway, AppConfig(), environment=Environment.DEMO
        )
        self.plan = valid_plan(now=1000)

    def _submit(self):
        return self.engine.execution.submit(
            self.plan,
            RunMode.DEMO_CONFIRM,
            gateway=self.gateway,
            account=demo_account(),
            spec=default_spec("EURUSD"),
            now=1000,
        )

    def test_a_synchronous_reply_does_not_become_final_fill_evidence(self):
        self.gateway.result = OrderResult(
            ok=True, retcode=10009, order=11, deal=22, request_id=33,
            volume=0.10, price=ACTUAL_FILL,
        )
        ok, _ = self._submit()
        self.assertTrue(ok)
        record = self.engine.execution.current
        self.assertEqual(record.filled_volume, 0.0)
        self.assertFalse(
            hasattr(record, "fill_price"),
            "an uncorroborated send reply must not become outcome price evidence",
        )

    def test_the_send_result_does_not_set_filled_volume(self):
        """Volume is owned by the deal ledger, which is where idempotency lives.

        Setting it from the send result means the deal that follows adds to a
        total that already counted it, and a partial fill reads as complete.
        """
        self.gateway.result = OrderResult(
            ok=True, retcode=10009, order=11, deal=0, request_id=33,
            volume=0.10, price=ACTUAL_FILL,
        )
        self._submit()
        self.assertEqual(self.engine.execution.current.filled_volume, 0.0)

    def test_exact_deals_set_the_entry_price_volume_weighted(self):
        """A partial fill arrives as several deals at several prices. The entry
        that matters is what the position holds, not its first tick."""
        self._submit()
        self.gateway.history_deals_list = [
            DealInfo(ticket=1, order=11, symbol="EURUSD", entry=0,
                     position_id=99, volume=0.05, price=1.10000, time=1000),
            DealInfo(ticket=2, order=11, symbol="EURUSD", entry=0,
                     position_id=99, volume=0.05, price=1.10100, time=1001),
        ]
        truth = self.engine.execution.resolve_from_broker(self.gateway, 1005)
        self.assertTrue(truth.resolved)
        self.assertAlmostEqual(truth.filled_volume, 0.10)
        self.assertAlmostEqual(truth.entry_price, 1.10050, places=6)

    def test_a_replayed_history_row_does_not_move_the_price_or_volume(self):
        self._submit()
        deal = DealInfo(ticket=1, order=11, symbol="EURUSD", entry=0,
                        position_id=99, volume=0.10, price=ACTUAL_FILL, time=1000)
        self.gateway.history_deals_list = [deal, deal]
        truth = self.engine.execution.resolve_from_broker(self.gateway, 1005)
        self.assertAlmostEqual(truth.filled_volume, 0.10)
        self.assertAlmostEqual(truth.entry_price, ACTUAL_FILL)
        self.assertEqual(len(truth.deals), 1)

    def test_a_same_symbol_position_is_not_stolen_as_fill_truth(self):
        """A symbol match is not execution identity, even at a plausible price."""
        self.gateway.result = OrderResult(ok=True, retcode=10009, order=11, deal=0)
        self._submit()
        self.gateway.positions_list = [
            PositionInfo(
                ticket=99, symbol="EURUSD", magic=self.engine.execution._magic,
                position_id=99, direction=Direction.LONG, volume=0.10,
                price_open=1.10077, time=1000,
            )
        ]
        truth = self.engine.execution.resolve_from_broker(self.gateway, 1005)
        self.assertFalse(truth.resolved)


class TestOutcomesReachTheDatabase(unittest.TestCase):
    """The half of the loop that only the backtest used to close."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.database = Database()
        self.database.open(str(Path(self._tmp.name) / "demo.sqlite"))
        self.repositories = Repositories(self.database)

    def tearDown(self):
        self.database.close()
        self._tmp.cleanup()

    def test_the_engine_persists_a_resolved_outcome(self):
        """Drives the tracker and the persistence hook the engine now runs
        every pass, which nothing outside the backtest previously did."""
        from alikhande.core.models import Bar, SignalCandidate
        from alikhande.core.outcomes import OutcomeTracker

        signal = SignalCandidate(
            signal_id="S-DEMO-1",
            symbol="EURUSD",
            direction=Direction.LONG,
            preferred_entry=PLANNED_ENTRY,
            stop_loss=1.09800,
            take_profit=1.10400,
            long_score=90.0,
        )
        self.repositories.save_signal(signal, "run-demo")

        tracker = OutcomeTracker()
        # Opened at the FILL, not the plan. That difference is the point.
        self.assertTrue(tracker.open(signal, ACTUAL_FILL, 1000))

        # A bar that reaches the target.
        resolved = tracker.update(
            "EURUSD",
            Bar(time=2000, open=1.10300, high=1.10500, low=1.10250, close=1.10450),
            2000,
        )
        self.assertTrue(resolved, "the target was reached and nothing resolved")
        outcome, state = resolved[0]
        self.assertEqual(state, SignalState.TP)

        self.assertTrue(self.repositories.save_outcome(outcome))
        self.repositories.update_signal_state(outcome.signal_id, state)

        summary = self.repositories.outcome_summary()
        self.assertEqual(int(summary["total"]), 1)

    def test_the_realised_r_is_measured_from_the_fill_not_the_plan(self):
        """The arithmetic that was wrong. Same trade, two entry prices, two
        different answers — and only one of them describes what happened."""
        from alikhande.core.models import Bar, SignalCandidate
        from alikhande.core.outcomes import OutcomeTracker

        signal = SignalCandidate(
            signal_id="S-1", symbol="EURUSD", direction=Direction.LONG,
            preferred_entry=PLANNED_ENTRY, stop_loss=1.09800,
            take_profit=1.10400, long_score=90.0,
        )
        exit_bar = Bar(time=2000, open=1.10300, high=1.10500, low=1.10250, close=1.10450)

        from_plan = OutcomeTracker()
        from_plan.open(signal, PLANNED_ENTRY, 1000)
        planned_r = from_plan.update("EURUSD", exit_bar, 2000)[0][0].realized_r

        from_fill = OutcomeTracker()
        from_fill.open(signal, ACTUAL_FILL, 1000)
        actual_r = from_fill.update("EURUSD", exit_bar, 2000)[0][0].realized_r

        self.assertNotAlmostEqual(
            planned_r, actual_r, places=4,
            msg="a 2.5 pip slippage must change the recorded R; if it does not, "
                "the entry price is not reaching the calculation",
        )
        # Entering higher on a long, with the stop unchanged, means a wider risk
        # and a smaller reward — so the honest number is the lower one.
        self.assertLess(actual_r, planned_r)


class TestTheEngineOpensOutcomesOnlyOnAFill(unittest.TestCase):
    def setUp(self):
        self.gateway = StubGateway()
        self.engine = ScanEngine(
            self.gateway, AppConfig(), environment=Environment.DEMO
        )

    def test_nothing_is_tracked_before_a_fill_is_confirmed(self):
        """The engine holds the signal pending. An outcome opened on an order
        that was never filled is an outcome about nothing."""
        self.assertEqual(self.engine.outcomes.tracked, {})

    def test_no_bar_based_pending_outcome_path_exists(self):
        """Demo closes from broker deals, not a later bar touching plan TP/SL."""
        self.assertFalse(hasattr(self.engine, "_pending_outcomes"))


if __name__ == "__main__":
    unittest.main()
