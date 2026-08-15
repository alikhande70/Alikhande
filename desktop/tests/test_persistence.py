"""Tests for the SQLite layer, run against a real sqlite3 database.

Not mocked. A schema test that mocks the database tests the mock.
"""

from __future__ import annotations

import tempfile
import unittest
import sqlite3
from pathlib import Path

from alikhande.adapters.sqlite.database import Database, SchemaTooNew, _V1_STATEMENTS
from alikhande.adapters.sqlite.repositories import Repositories
from alikhande.core.enums import Direction, ExecState, RuntimeKind, SetupType, SignalState
from alikhande.core.journal import Event, Journal, Level
from alikhande.core.models import (
    ExecutionRecord,
    Outcome,
    RiskState,
    SignalCandidate,
    SymbolSpec,
    TradePlan,
)
from alikhande.version import DB_SCHEMA_VERSION


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = str(Path(self._dir.name) / "test.sqlite")
        self.db = Database()
        self.db.open(self.path)
        self.repo = Repositories(self.db)

    def tearDown(self):
        self.db.close()
        self._dir.cleanup()

    def signal(self, signal_id="S1", symbol="EURUSD", setup=SetupType.TREND_PULLBACK):
        return SignalCandidate(
            signal_id=signal_id, symbol=symbol, direction=Direction.LONG, setup=setup,
            state=SignalState.CONFIRMED, preferred_entry=1.10, stop_loss=1.098,
            take_profit=1.104, creation_time=1000, expires_at=1900,
            rule_version="RULE-TEST", scoring_version="SCORE-TEST",
            parameter_hash="PH", broker_spec_hash="BH",
        )


class TestSchema(DatabaseCase):
    def test_migrates_to_the_current_version(self):
        row = self.db.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        self.assertEqual(int(row["value"]), DB_SCHEMA_VERSION)

    def test_creates_every_expected_table(self):
        rows = self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r["name"] for r in rows}
        for table in (
            "runs", "signals", "signal_features", "trade_plans", "executions",
            "deals", "outcomes", "symbol_specs", "risk_state", "runtime_events",
        ):
            self.assertIn(table, names)

    def test_migration_is_idempotent(self):
        self.db.migrate()
        self.db.migrate()
        self.assertTrue(self.db.is_open)

    def test_refuses_a_database_from_a_newer_build(self):
        """Operating against an unknown shape is how a migration drops columns."""
        self.db.execute(
            "INSERT OR REPLACE INTO schema_meta(key,value) VALUES('schema_version','999')"
        )
        self.db.commit()
        with self.assertRaises(SchemaTooNew):
            self.db.migrate()

    def test_reopening_an_existing_file_works(self):
        self.db.close()
        again = Database()
        self.assertTrue(again.open(self.path))
        again.close()

    def test_v1_migration_preserves_previously_valid_outcome(self):
        path = str(Path(self._dir.name) / "legacy.sqlite")
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        for statement in _V1_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_meta VALUES('schema_version','1')"
        )
        connection.execute(
            "INSERT INTO signals(signal_id,symbol,direction,setup,state,created_at,"
            " rule_version,scoring_version,parameter_hash,broker_spec_hash)"
            " VALUES('LEGACY','EURUSD',1,1,'TP',1,'RULE-TEST','S','P','B')"
        )
        connection.execute(
            "INSERT INTO outcomes(signal_id,result,realized_r,closed_at)"
            " VALUES('LEGACY','TP',2.0,2)"
        )
        connection.commit()
        connection.close()

        migrated = Database()
        migrated.open(path)
        repo = Repositories(migrated)
        self.assertEqual(repo.outcome_counts("EURUSD", 1, "RULE-TEST"), (1, 1))
        row = migrated.execute(
            "SELECT source, valid_for_statistics FROM outcomes WHERE signal_id='LEGACY'"
        ).fetchone()
        self.assertEqual(row["source"], "LEGACY")
        self.assertEqual(row["valid_for_statistics"], 1)
        migrated.close()


class TestSignals(DatabaseCase):
    def test_saves_and_finds_a_signal(self):
        self.assertTrue(self.repo.save_signal(self.signal(), "RUN1"))
        self.assertTrue(self.repo.signal_exists("S1"))
        self.assertFalse(self.repo.signal_exists("nope"))

    def test_re_saving_keeps_the_first_sighting(self):
        """Identity is the structural situation; the first timestamp is the one
        any later analysis depends on."""
        self.repo.save_signal(self.signal(), "RUN1")
        second = self.signal()
        second.creation_time = 9999
        self.repo.save_signal(second, "RUN1")
        row = self.db.execute("SELECT created_at FROM signals WHERE signal_id='S1'").fetchone()
        self.assertEqual(row["created_at"], 1000)

    def test_hash_collision_is_refused_without_overwriting_evidence(self):
        from alikhande.adapters.sqlite.repositories import SignalIdentityCollision

        original = self.signal(signal_id="COLLISION", symbol="EURUSD")
        original.confirmation_bar_time = 100
        self.repo.save_signal(original, "RUN1")
        different = self.signal(signal_id="COLLISION", symbol="GBPUSD")
        different.confirmation_bar_time = 200
        with self.assertRaises(SignalIdentityCollision):
            self.repo.save_signal(different, "RUN2")
        row = self.db.execute(
            "SELECT symbol, confirmation_bar_time FROM signals WHERE signal_id='COLLISION'"
        ).fetchone()
        self.assertEqual((row["symbol"], row["confirmation_bar_time"]), ("EURUSD", 100))

    def test_same_structure_with_different_experiment_metadata_is_a_collision(self):
        from alikhande.adapters.sqlite.repositories import SignalIdentityCollision

        original = self.signal(signal_id="EXPERIMENT")
        self.repo.save_signal(original, "RUN1")
        changed = self.signal(signal_id="EXPERIMENT")
        changed.parameter_hash = "OTHER-PARAMETERS"
        with self.assertRaises(SignalIdentityCollision):
            self.repo.save_signal(changed, "RUN2")
        changed = self.signal(signal_id="EXPERIMENT")
        changed.broker_spec_hash = "OTHER-CONTRACT"
        with self.assertRaises(SignalIdentityCollision):
            self.repo.save_signal(changed, "RUN3")

    def test_state_transitions_are_stored(self):
        self.repo.save_signal(self.signal(), "RUN1")
        self.repo.update_signal_state("S1", SignalState.PREVIEWED)
        self.assertEqual(self.repo.signal_state("S1"), SignalState.PREVIEWED)

    def test_terminal_signal_cannot_be_reopened_or_relabelled(self):
        self.repo.save_signal(self.signal(), "RUN1")
        self.assertTrue(self.repo.update_signal_state("S1", SignalState.PREVIEWED))
        self.assertTrue(self.repo.update_signal_state("S1", SignalState.NOT_FILLED))
        self.assertFalse(self.repo.update_signal_state("S1", SignalState.PREVIEWED))
        self.assertFalse(self.repo.update_signal_state("S1", SignalState.TP))
        self.assertEqual(self.repo.signal_state("S1"), SignalState.NOT_FILLED)

    def test_features_are_stored_and_replaced(self):
        self.repo.save_signal(self.signal(), "RUN1")
        self.repo.save_features("S1", {"h1_adx": 25.0, "h1_atr": 0.001})
        self.repo.save_features("S1", {"h1_adx": 30.0})
        row = self.db.execute(
            "SELECT value FROM signal_features WHERE signal_id='S1' AND name='h1_adx'"
        ).fetchone()
        self.assertAlmostEqual(row["value"], 30.0)


class TestExecutions(DatabaseCase):
    def record(self, terminal=False, state=ExecState.FILLED, execution_id="E1"):
        return ExecutionRecord(
            execution_id=execution_id, plan_id="P1", signal_id="S1", symbol="EURUSD",
            state=state, order_ticket=11, requested_volume=0.1, filled_volume=0.1,
            created_at=1000, updated_at=1000, terminal=terminal,
        )

    def test_an_unresolved_execution_is_recoverable(self):
        self.repo.save_execution(self.record(terminal=False))
        loaded = self.repo.load_unresolved_execution()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.execution_id, "E1")
        self.assertFalse(loaded.terminal)

    def test_a_resolved_execution_is_not_recovered(self):
        self.repo.save_execution(self.record(terminal=True, state=ExecState.COMPLETED))
        self.assertIsNone(self.repo.load_unresolved_execution())

    def test_terminal_rejection_without_outcome_is_recovered_for_evidence(self):
        self.repo.save_execution(self.record(terminal=True, state=ExecState.REJECTED))
        loaded = self.repo.load_execution_awaiting_outcome()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.state, ExecState.REJECTED)

    def test_an_unparseable_stored_state_becomes_unknown_not_finished(self):
        """A corrupt row must keep the gate shut, not open it."""
        self.repo.save_execution(self.record(terminal=False))
        self.db.execute("UPDATE executions SET state='GIBBERISH' WHERE execution_id='E1'")
        self.db.commit()
        loaded = self.repo.load_unresolved_execution()
        self.assertEqual(loaded.state, ExecState.UNKNOWN)
        self.assertFalse(loaded.terminal)


class TestDealIdempotency(DatabaseCase):
    def row(self, ticket):
        return dict(
            execution_id="E1", symbol="EURUSD", entry=0, volume=0.1,
            price=1.1, net_profit=0.0, recorded_at=1000,
        )

    def test_a_ticket_is_admitted_exactly_once(self):
        self.assertTrue(self.repo.record_deal_once(42, **self.row(42)))
        self.assertFalse(self.repo.record_deal_once(42, **self.row(42)))

    def test_admission_survives_a_reopen(self):
        """The durable answer to 'have I already counted this fill?'."""
        self.assertTrue(self.repo.record_deal_once(42, **self.row(42)))
        self.db.close()

        again = Database()
        again.open(self.path)
        repo = Repositories(again)
        self.assertFalse(repo.record_deal_once(42, **self.row(42)))
        self.assertIn(42, repo.known_deal_tickets())
        again.close()

    def test_a_zero_ticket_is_refused(self):
        self.assertFalse(self.repo.record_deal_once(0, **self.row(0)))


class TestOutcomes(DatabaseCase):
    def test_outcome_and_terminal_state_commit_as_one_unit(self):
        self.repo.save_signal(self.signal(), "RUN1")
        self.repo.update_signal_state("S1", SignalState.PREVIEWED)
        self.repo.update_signal_state("S1", SignalState.ACTIVE)
        outcome = Outcome(
            signal_id="S1", result="TP", execution_id="E1", source="LIVE_DEMO",
            evidence_quality="BROKER_DEALS", valid_for_statistics=True, closed_at=2,
        )
        self.assertTrue(self.repo.save_outcome_with_state(outcome, SignalState.TP))
        self.assertEqual(self.repo.signal_state("S1"), SignalState.TP)
        self.assertEqual(self.repo.outcome_for_execution("E1").result, "TP")

    def test_illegal_terminal_commit_writes_neither_half(self):
        self.repo.save_signal(self.signal(), "RUN1")
        outcome = Outcome(
            signal_id="S1", result="TP", execution_id="E1", source="LIVE_DEMO",
            evidence_quality="BROKER_DEALS", valid_for_statistics=True, closed_at=2,
        )
        self.assertFalse(self.repo.save_outcome_with_state(outcome, SignalState.TP))
        self.assertEqual(self.repo.signal_state("S1"), SignalState.CONFIRMED)
        self.assertIsNone(self.repo.outcome_for_execution("E1"))

    def test_a_duplicate_cannot_overwrite_previous_valid_evidence(self):
        self.repo.save_signal(self.signal(), "RUN1")
        first = Outcome(
            signal_id="S1", result="TP", realized_r=2.0,
            execution_id="E1", source="LIVE_DEMO", evidence_quality="BROKER_DEALS",
            valid_for_statistics=True, closed_at=1000,
        )
        self.assertTrue(self.repo.save_outcome(first))
        self.assertFalse(
            self.repo.save_outcome(
                Outcome(
                    signal_id="S1", result="SL", realized_r=-1.0,
                    execution_id="E1", source="ERROR", valid_for_statistics=False,
                    closed_at=2000,
                )
            )
        )
        stored = self.repo.outcome_for_execution("E1")
        self.assertEqual(stored.result, "TP")
        self.assertTrue(stored.valid_for_statistics)

    def test_counts_are_scoped_by_rule_version(self):
        """Mixing versions describes a system that never ran."""
        for i in range(4):
            signal = self.signal(signal_id=f"S{i}")
            signal.rule_version = "RULE-A" if i < 2 else "RULE-B"
            self.repo.save_signal(signal, "RUN1")
            self.repo.save_outcome(
                Outcome(signal_id=f"S{i}", result="TP" if i % 2 == 0 else "SL", closed_at=1)
            )

        wins, total = self.repo.outcome_counts("EURUSD", int(SetupType.TREND_PULLBACK), "RULE-A")
        self.assertEqual((wins, total), (1, 2))
        wins, total = self.repo.outcome_counts("EURUSD", int(SetupType.TREND_PULLBACK), "RULE-B")
        self.assertEqual((wins, total), (1, 2))

    def test_only_tp_and_sl_are_counted(self):
        """Expiry says something about the scanner, not the setup's edge."""
        for i, result in enumerate(("TP", "SL", "EXPIRED", "INVALIDATED", "NOT_FILLED")):
            self.repo.save_signal(self.signal(signal_id=f"S{i}"), "RUN1")
            self.repo.save_outcome(Outcome(signal_id=f"S{i}", result=result, closed_at=1))

        wins, total = self.repo.outcome_counts(
            "EURUSD", int(SetupType.TREND_PULLBACK), "RULE-TEST"
        )
        self.assertEqual((wins, total), (1, 2))

    def test_counts_are_scoped_by_symbol_and_setup(self):
        self.repo.save_signal(self.signal(signal_id="A", symbol="EURUSD"), "RUN1")
        self.repo.save_signal(self.signal(signal_id="B", symbol="GBPUSD"), "RUN1")
        self.repo.save_outcome(Outcome(signal_id="A", result="TP", closed_at=1))
        self.repo.save_outcome(Outcome(signal_id="B", result="TP", closed_at=1))
        self.assertEqual(
            self.repo.outcome_counts("EURUSD", int(SetupType.TREND_PULLBACK), "RULE-TEST"),
            (1, 1),
        )

    def test_an_empty_database_reports_zero_not_a_rate(self):
        summary = self.repo.outcome_summary()
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["avg_r"], 0.0)

    def test_summary_aggregates_r(self):
        for i, (result, r) in enumerate((("TP", 2.0), ("SL", -1.0), ("TP", 2.0))):
            self.repo.save_signal(self.signal(signal_id=f"S{i}"), "RUN1")
            self.repo.save_outcome(
                Outcome(signal_id=f"S{i}", result=result, realized_r=r, closed_at=1)
            )
        summary = self.repo.outcome_summary()
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["wins"], 2)
        self.assertAlmostEqual(summary["sum_r"], 3.0)
        self.assertAlmostEqual(summary["avg_r"], 1.0)


class TestRiskStateAndSpecs(DatabaseCase):
    def test_risk_state_round_trips(self):
        state = RiskState(
            day_key=2026001, day_start_equity=10_000.0, peak_equity=12_000.0,
            consecutive_losses=3, daily_risk_used_pct=0.75, updated_at=1000,
        )
        self.repo.save_risk_state(state)
        loaded = self.repo.load_risk_state()
        self.assertEqual(loaded.peak_equity, 12_000.0)
        self.assertEqual(loaded.consecutive_losses, 3)

    def test_risk_state_is_a_single_row(self):
        self.repo.save_risk_state(RiskState(peak_equity=1.0, updated_at=1))
        self.repo.save_risk_state(RiskState(peak_equity=2.0, updated_at=2))
        rows = self.db.execute("SELECT COUNT(*) AS n FROM risk_state").fetchone()
        self.assertEqual(rows["n"], 1)
        self.assertEqual(self.repo.load_risk_state().peak_equity, 2.0)

    def test_spec_fingerprint_detects_drift(self):
        spec = SymbolSpec(symbol="EURUSD", fingerprint="AAA", ready=True)
        self.repo.save_spec(spec, 1000)
        self.assertEqual(self.repo.spec_fingerprint("EURUSD"), "AAA")

        spec.fingerprint = "BBB"
        self.repo.save_spec(spec, 2000)
        self.assertEqual(self.repo.spec_fingerprint("EURUSD"), "BBB")
        self.assertIsNone(self.repo.spec_fingerprint("GBPUSD"))


class TestEvidenceReplacement(DatabaseCase):
    def _seed_previous(self) -> None:
        self.repo.start_run(
            "OLD", RuntimeKind.REPLAY.name, False, "1", "RULE-TEST", "SCORE",
            "PARAM", "EURUSD", 1,
        )
        self.repo.save_signal(self.signal("OLD-SIGNAL"), "OLD")
        self.repo.save_outcome(
            Outcome(signal_id="OLD-SIGNAL", result="TP", realized_r=2.0, closed_at=2)
        )
        self.repo.finish_run("OLD", 3)

    def test_unfinished_staging_cannot_delete_previous_evidence(self):
        self._seed_previous()
        with tempfile.TemporaryDirectory() as folder:
            staged = Database()
            staged.open(str(Path(folder) / "stage.sqlite"))
            stage_repo = Repositories(staged)
            stage_repo.start_run(
                "NEW", RuntimeKind.REPLAY.name, False, "1", "RULE-TEST", "SCORE",
                "PARAM", "EURUSD", 10,
            )
            staged.close()
            with self.assertRaises(ValueError):
                self.repo.replace_runs_of_kind_from(
                    str(Path(folder) / "stage.sqlite"), RuntimeKind.REPLAY.name
                )
        self.assertEqual(self.repo.outcome_summary()["total"], 1)
        self.assertTrue(self.repo.signal_exists("OLD-SIGNAL"))

    def test_complete_staging_replaces_replay_in_one_commit(self):
        self._seed_previous()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "stage.sqlite")
            staged = Database()
            staged.open(path)
            stage_repo = Repositories(staged)
            stage_repo.start_run(
                "NEW", RuntimeKind.REPLAY.name, False, "1", "RULE-TEST", "SCORE",
                "PARAM", "EURUSD", 10,
            )
            stage_repo.save_signal(self.signal("NEW-SIGNAL"), "NEW")
            stage_repo.save_outcome(
                Outcome(signal_id="NEW-SIGNAL", result="SL", realized_r=-1.0, closed_at=11)
            )
            stage_repo.finish_run("NEW", 12)
            staged.close()
            self.assertEqual(
                self.repo.replace_runs_of_kind_from(path, RuntimeKind.REPLAY.name), 1
            )
        self.assertFalse(self.repo.signal_exists("OLD-SIGNAL"))
        self.assertTrue(self.repo.signal_exists("NEW-SIGNAL"))
        self.assertEqual(self.repo.outcome_summary()["losses"], 1)

    def test_copy_failure_rolls_back_the_replay_purge(self):
        self._seed_previous()
        self.repo.start_run(
            "LIVE", RuntimeKind.LIVE.name, True, "1", "RULE-TEST", "SCORE",
            "PARAM", "EURUSD", 20,
        )
        self.repo.save_signal(self.signal("COLLIDE"), "LIVE")
        self.repo.finish_run("LIVE", 21)

        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "stage.sqlite")
            staged = Database()
            staged.open(path)
            stage_repo = Repositories(staged)
            stage_repo.start_run(
                "NEW", RuntimeKind.REPLAY.name, False, "1", "RULE-TEST", "SCORE",
                "PARAM", "EURUSD", 10,
            )
            # Collides only after the target transaction has begun and its old
            # replay rows have been deleted. The rollback must restore them.
            stage_repo.save_signal(self.signal("COLLIDE"), "NEW")
            stage_repo.finish_run("NEW", 12)
            staged.close()
            with self.assertRaises(sqlite3.IntegrityError):
                self.repo.replace_runs_of_kind_from(path, RuntimeKind.REPLAY.name)

        self.assertTrue(self.repo.run_exists("OLD"))
        self.assertTrue(self.repo.signal_exists("OLD-SIGNAL"))
        self.assertTrue(self.repo.run_exists("LIVE"))
        self.assertTrue(self.repo.signal_exists("COLLIDE"))
        self.assertEqual(self.repo.outcome_summary()["total"], 1)

    def test_cancelled_atomic_backtest_preserves_previous_evidence(self):
        from alikhande.adapters.offline.gateway import OfflineGateway
        from alikhande.app.backtest import (
            BACKTEST_TIMEFRAMES,
            Backtester,
            run_with_atomic_persistence,
        )

        self._seed_previous()
        gateway = OfflineGateway()
        gateway.load_synthetic(("EURUSD",), BACKTEST_TIMEFRAMES, 260, seed=7)
        result = run_with_atomic_persistence(
            Backtester(),
            gateway,
            ("EURUSD",),
            target_database=self.path,
            warmup_bars=9_000,
            progress=lambda *_: False,
        )
        self.assertTrue(result.cancelled)
        self.assertFalse(result.evidence_committed)
        self.assertEqual(self.repo.outcome_summary()["total"], 1)
        self.assertTrue(self.repo.signal_exists("OLD-SIGNAL"))

    def test_backtest_error_never_opens_the_target_database(self):
        from alikhande.adapters.offline.gateway import OfflineGateway
        from alikhande.app.backtest import run_with_atomic_persistence

        self._seed_previous()

        class ExplodingBacktester:
            def run(self, *_args, **_kwargs):
                raise RuntimeError("injected replay failure")

        with self.assertRaisesRegex(RuntimeError, "injected"):
            run_with_atomic_persistence(
                ExplodingBacktester(),
                OfflineGateway(),
                ("EURUSD",),
                target_database=self.path,
            )
        self.assertEqual(self.repo.outcome_summary()["total"], 1)
        self.assertTrue(self.repo.signal_exists("OLD-SIGNAL"))

    def test_duplicate_run_id_is_refused_without_deleting_previous_run(self):
        from alikhande.adapters.offline.gateway import OfflineGateway
        from alikhande.app.backtest import Backtester

        self._seed_previous()
        with self.assertRaisesRegex(ValueError, "already exists"):
            Backtester().run(
                OfflineGateway(),
                ("EURUSD",),
                repositories=self.repo,
                run_id="OLD",
            )
        self.assertTrue(self.repo.run_exists("OLD"))
        self.assertTrue(self.repo.signal_exists("OLD-SIGNAL"))
        self.assertEqual(self.repo.outcome_summary()["total"], 1)


class TestEventJournal(DatabaseCase):
    def test_events_persist_and_reload(self):
        self.repo.log_event(Event(ts=1, level=Level.WARN, code="C", context="EURUSD", message="m"))
        events = self.repo.recent_events(10)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].level, Level.WARN)
        self.assertEqual(events[0].code, "C")

    def test_the_journal_forwards_to_the_sink(self):
        journal = Journal(sink=self.repo.log_event)
        journal.error("BOOM", "EURUSD", "something broke", 1000)
        self.assertEqual(len(self.repo.recent_events(10)), 1)

    def test_repeats_are_suppressed_and_counted(self):
        """A refusal logged every 250ms is the same as no log at all."""
        journal = Journal(suppress_seconds=60)
        self.assertIsNotNone(journal.info("CODE", "EURUSD", "m", 1000))
        self.assertIsNone(journal.info("CODE", "EURUSD", "m", 1001))
        self.assertIsNone(journal.info("CODE", "EURUSD", "m", 1030))
        event = journal.info("CODE", "EURUSD", "m", 1100)
        self.assertIsNotNone(event)
        self.assertEqual(event.repeats, 2)
        self.assertEqual(len(journal.entries()), 2)

    def test_distinct_codes_are_not_suppressed_together(self):
        journal = Journal(suppress_seconds=60)
        self.assertIsNotNone(journal.info("A", "", "m", 1000))
        self.assertIsNotNone(journal.info("B", "", "m", 1000))

    def test_the_journal_is_bounded(self):
        journal = Journal(capacity=10, suppress_seconds=0)
        for i in range(50):
            journal.info(f"CODE{i}", "", "m", 1000 + i)
        self.assertLessEqual(len(journal.entries()), 10)


class TestWithoutDatabase(unittest.TestCase):
    """Every repository method must degrade rather than raise.

    An offline session has no database and must still run — a scanner that
    crashes because it cannot persist is worse than one that scans silently.
    """

    def test_methods_return_falsey_when_closed(self):
        repo = Repositories(Database())
        self.assertFalse(repo.ready)
        self.assertFalse(repo.signal_exists("x"))
        self.assertFalse(repo.save_signal(SignalCandidate()))
        self.assertFalse(repo.save_plan(TradePlan()))
        self.assertFalse(repo.save_execution(ExecutionRecord()))
        self.assertFalse(repo.save_outcome(Outcome()))
        self.assertFalse(repo.save_risk_state(RiskState()))
        self.assertIsNone(repo.load_risk_state())
        self.assertIsNone(repo.load_unresolved_execution())
        self.assertEqual(repo.outcome_counts("EURUSD", 1, "R"), (0, 0))
        self.assertEqual(repo.recent_events(), [])
        self.assertEqual(repo.known_deal_tickets(), [])


if __name__ == "__main__":
    unittest.main()
