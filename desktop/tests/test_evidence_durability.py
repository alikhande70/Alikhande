"""A cancelled run must not destroy the evidence it failed to replace.

Both the CLI calibration and the Backtest view purged the previous replay
*before* starting the new one, on the reasoning that calibration should replace
rather than accumulate. The reasoning is right and the order was wrong: an
operator who pressed Stop, or a replay that raised halfway, or a Ctrl-C, was
left with no calibration at all and nothing to restore it from — the previous
evidence destroyed by an action that produced none.

The order is now: write the new run under its own id, and only once it has
finished replace the others. A cancelled run is discarded rather than kept,
because a truncated sample stored under the same label as a complete one is
indistinguishable from it afterwards.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alikhande.adapters.sqlite.database import Database
from alikhande.adapters.sqlite.repositories import Repositories
from alikhande.core.enums import Direction, RuntimeKind, SetupType
from alikhande.core.models import Outcome, SignalCandidate

try:  # pragma: no cover - depends on how the suite was launched
    from .sourcecheck import method_source, module_source
except ImportError:  # pragma: no cover
    from sourcecheck import method_source, module_source


class EvidenceTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.database = Database()
        self.database.open(str(Path(self._tmp.name) / "evidence.sqlite"))
        self.repositories = Repositories(self.database)

    def tearDown(self):
        self.database.close()
        self._tmp.cleanup()

    def seed_run(self, run_id: str, count: int, kind=RuntimeKind.REPLAY) -> None:
        """Write a run with ``count`` signals, each carrying one outcome."""
        self.repositories.start_run(
            run_id=run_id,
            kind=kind.name,
            is_production=False,
            app_version="2.2.0",
            rule_version="RULE-2.0.0-PY",
            scoring_version="SCORE-2.0.0",
            parameter_hash="test",
            symbols="EURUSD",
            started_at=1000,
        )
        for index in range(count):
            signal_id = f"{run_id}-S{index}"
            self.repositories.save_signal(
                SignalCandidate(
                    signal_id=signal_id,
                    symbol="EURUSD",
                    direction=Direction.LONG,
                    setup=SetupType.TREND_PULLBACK,
                    preferred_entry=1.1,
                    stop_loss=1.098,
                    take_profit=1.104,
                    long_score=90.0,
                ),
                run_id,
            )
            self.repositories.save_outcome(
                Outcome(
                    signal_id=signal_id,
                    result="TP",
                    realized_r=1.0,
                    mfe_r=1.2,
                    mae_r=-0.3,
                    closed_at=2000,
                )
            )

    def outcome_total(self) -> int:
        return int(self.repositories.outcome_summary()["total"])


class TestReplacementIsAtomic(EvidenceTestCase):
    def test_a_completed_run_replaces_the_previous_one(self):
        """The behaviour that was always correct, and must stay correct."""
        self.seed_run("old", 5)
        self.assertEqual(self.outcome_total(), 5)

        self.seed_run("new", 3)
        self.assertEqual(self.outcome_total(), 8, "both runs should coexist mid-flight")

        removed = self.repositories.purge_runs_of_kind(
            RuntimeKind.REPLAY.name, keep_run_id="new"
        )
        self.assertEqual(removed, 5)
        self.assertEqual(self.outcome_total(), 3, "only the new run should remain")

    def test_a_cancelled_run_leaves_the_previous_evidence_intact(self):
        """The defect. Purging first meant a Stop press erased the calibration
        and replaced it with nothing."""
        self.seed_run("old", 5)
        self.seed_run("partial", 2)  # cancelled halfway

        self.repositories.purge_run("partial")

        self.assertEqual(
            self.outcome_total(), 5, "cancelling destroyed the previous calibration"
        )

    def test_a_failed_run_leaves_the_previous_evidence_intact(self):
        self.seed_run("old", 4)
        try:
            self.seed_run("doomed", 1)
            raise RuntimeError("the replay raised")
        except RuntimeError:
            self.repositories.purge_run("doomed")
        self.assertEqual(self.outcome_total(), 4)

    def test_the_partial_run_is_not_kept(self):
        """A truncated sample stored under the same label as a complete one is
        indistinguishable from it afterwards."""
        self.seed_run("partial", 3)
        self.repositories.purge_run("partial")
        self.assertEqual(self.outcome_total(), 0)

    def test_purging_a_run_that_does_not_exist_is_harmless(self):
        self.seed_run("old", 3)
        self.assertEqual(self.repositories.purge_run("never-existed"), 0)
        self.assertEqual(self.outcome_total(), 3)

    def test_purging_with_no_keep_still_clears_everything(self):
        """The original signature still works — the calibration path uses it
        nowhere now, but the guarantee it made has not changed."""
        self.seed_run("a", 2)
        self.seed_run("b", 2)
        self.repositories.purge_runs_of_kind(RuntimeKind.REPLAY.name)
        self.assertEqual(self.outcome_total(), 0)


class TestALiveRunIsNeverTouched(EvidenceTestCase):
    """The one thing purging must never reach.

    Replay evidence can be regenerated by running the replay again. A demo
    account's outcomes took weeks of real market time and cannot be recreated
    at all.
    """

    def test_purging_replays_leaves_live_outcomes_alone(self):
        self.seed_run("live-session", 6, kind=RuntimeKind.LIVE)
        self.seed_run("replay", 4, kind=RuntimeKind.REPLAY)
        self.assertEqual(self.outcome_total(), 10)

        self.repositories.purge_runs_of_kind(RuntimeKind.REPLAY.name)
        self.assertEqual(self.outcome_total(), 6, "a LIVE run was destroyed")

    def test_purging_a_replay_run_by_id_cannot_reach_a_live_one(self):
        self.seed_run("live-session", 3, kind=RuntimeKind.LIVE)
        self.repositories.purge_run("replay-that-was-never-written")
        self.assertEqual(self.outcome_total(), 3)


class TestTheCallersUseTheSafeOrder(unittest.TestCase):
    """Source-level, because reproducing a mid-replay Ctrl-C in a test is more
    machinery than the property is worth — and this catches a regression at the
    moment it is written rather than the moment it costs somebody a week of
    demo history."""

    def test_the_backtest_view_purges_only_after_the_run(self):
        # From disk: importing the view pulls in PySide6, which is unimportable
        # in the dependency-free job — and this guard is worth running there.
        body = module_source("ui", "views", "backtest.py")
        purge_at = body.index("purge_runs_of_kind")
        run_at = body.index("Backtester(config).run")
        self.assertLess(
            run_at, purge_at, "the view still purges before it replays"
        )
        self.assertIn("keep_run_id", body)
        self.assertIn("purge_run(run_id)", body)

    def test_the_calibration_command_purges_only_after_the_run(self):
        body = method_source(module_source("__main__.py"), "_cmd_calibrate")
        purge_at = body.index("purge_runs_of_kind")
        run_at = body.index("Backtester(config).run")
        self.assertLess(run_at, purge_at, "calibrate still purges before it replays")
        self.assertIn("keep_run_id", body)

    def test_the_calibration_command_cleans_up_on_a_keyboard_interrupt(self):
        """`except Exception` would miss Ctrl-C, which is the interruption an
        operator is most likely to cause."""
        body = method_source(module_source("__main__.py"), "_cmd_calibrate")
        self.assertIn("except BaseException", body)
        self.assertIn("purge_run(run_id)", body)


if __name__ == "__main__":
    unittest.main()
