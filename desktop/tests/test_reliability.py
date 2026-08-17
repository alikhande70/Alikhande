"""Connection supervision, data quality, order errors, recovery, notifications
and maintenance.

These are the subsystems that only matter on a bad day, which is exactly why
they are tested against bad days rather than good ones: a link that flaps for
six hours, a feed that freezes while reporting perfect latency, a backup taken
from a database that is being written to.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from alikhande.app.maintenance import (
    SETTINGS_FORMAT,
    backup_database,
    diagnostics,
    export_settings,
    import_settings,
    list_backups,
    prune_backups,
    restore_database,
)
from alikhande.core.dataquality import (
    DataQualityMonitor,
    Grade,
    inspect_series,
    severity_of,
)
from alikhande.core.enums import Timeframe
from alikhande.core.notifications import (
    Channel,
    NotificationRouter,
    NotificationSettings,
    Urgency,
)
from alikhande.core.order_errors import ErrorCategory, ErrorTally, classify, is_success
from alikhande.core.recovery import (
    ExitKind,
    SessionLedger,
    SessionRecord,
    assess,
)
from alikhande.core.supervision import (
    MAX_BACKOFF_SECONDS,
    ConnectionSupervisor,
    LinkState,
    Probe,
    summarise,
)


# ===========================================================================
class TestConnectionSupervision(unittest.TestCase):
    def setUp(self):
        self.supervisor = ConnectionSupervisor()

    def _tick(self, count, now_start=1000, **kwargs):
        """Feed ``count`` successful probes with advancing server time."""
        for i in range(count):
            self.supervisor.observe(
                Probe(ok=True, latency_ms=kwargs.get("latency_ms", 20.0), server_time=2000 + i),
                now_start + i,
            )

    def test_a_good_link_is_healthy(self):
        self._tick(5)
        self.assertEqual(self.supervisor.health.state, LinkState.HEALTHY)
        self.assertTrue(self.supervisor.health.usable)

    def test_one_failure_is_degraded_not_disconnected(self):
        """A single failed call during the terminal's own reconnect is
        ordinary and must not repaint the window."""
        self._tick(3)
        self.supervisor.observe(Probe(ok=False, detail="timeout"), 1010)
        self.assertEqual(self.supervisor.health.state, LinkState.DEGRADED)

    def test_two_failures_are_a_disconnection(self):
        self.supervisor.observe(Probe(ok=False), 1000)
        self.supervisor.observe(Probe(ok=False), 1001)
        self.assertEqual(self.supervisor.health.state, LinkState.DISCONNECTED)
        self.assertFalse(self.supervisor.health.usable)

    def test_a_frozen_feed_with_perfect_latency_is_stalled(self):
        """The failure mode this module exists for.

        Every call answers, every call is fast, and every call returns the same
        server time. A boolean ``is_connected()`` reports this as healthy
        forever.
        """
        for i in range(200):
            self.supervisor.observe(Probe(ok=True, latency_ms=5.0, server_time=2000), 1000 + i)
        self.assertEqual(self.supervisor.health.state, LinkState.STALLED)
        self.assertFalse(self.supervisor.health.usable)

    def test_a_stall_clears_when_the_feed_moves_again(self):
        for i in range(200):
            self.supervisor.observe(Probe(ok=True, latency_ms=5.0, server_time=2000), 1000 + i)
        self.assertEqual(self.supervisor.health.state, LinkState.STALLED)
        self.supervisor.observe(Probe(ok=True, latency_ms=5.0, server_time=2001), 1300)
        self.assertEqual(self.supervisor.health.state, LinkState.HEALTHY)

    def test_a_missing_server_time_does_not_reset_the_stall_clock(self):
        """A gateway that stops reporting time must not look permanently fresh."""
        for i in range(100):
            self.supervisor.observe(Probe(ok=True, latency_ms=5.0, server_time=2000), 1000 + i)
        stalled_for = self.supervisor.health.stalled_for
        self.supervisor.observe(Probe(ok=True, latency_ms=5.0, server_time=0), 1200)
        self.assertGreaterEqual(self.supervisor.health.stalled_for, stalled_for)

    def test_slow_but_answering_is_degraded_and_still_usable(self):
        """Refusing to scan because a pass took 900ms would make the
        application useless on an ordinary laptop."""
        self._tick(3, latency_ms=1200.0)
        self.assertEqual(self.supervisor.health.state, LinkState.DEGRADED)
        self.assertTrue(self.supervisor.health.usable)

    def test_backoff_grows_then_caps(self):
        for attempt in range(20):
            self.supervisor.record_attempt(1000 + attempt, succeeded=False)
        self.assertEqual(self.supervisor.backoff_seconds(), MAX_BACKOFF_SECONDS)

    def test_backoff_is_zero_before_any_attempt(self):
        self.assertEqual(self.supervisor.backoff_seconds(), 0)

    def test_a_successful_attempt_does_not_declare_health_by_itself(self):
        """``initialize()`` returning true says nothing about whether later
        calls will work. Only a probe decides."""
        self.supervisor.observe(Probe(ok=False), 1000)
        self.supervisor.observe(Probe(ok=False), 1001)
        self.supervisor.record_attempt(1002, succeeded=True)
        self.assertEqual(self.supervisor.health.state, LinkState.DISCONNECTED)

    def test_reconnect_is_attempted_when_stalled_not_only_when_disconnected(self):
        for i in range(200):
            self.supervisor.observe(Probe(ok=True, latency_ms=5.0, server_time=2000), 1000 + i)
        self.assertTrue(self.supervisor.should_reconnect(1300))

    def test_reconnect_waits_out_the_backoff(self):
        self.supervisor.observe(Probe(ok=False), 1000)
        self.supervisor.observe(Probe(ok=False), 1001)
        self.supervisor.record_attempt(1001, succeeded=False)
        self.assertFalse(self.supervisor.should_reconnect(1001))
        self.assertTrue(self.supervisor.should_reconnect(1001 + MAX_BACKOFF_SECONDS))

    def test_a_healthy_link_never_reconnects(self):
        self._tick(5)
        self.assertFalse(self.supervisor.should_reconnect(9_999_999))

    def test_history_records_transitions_not_every_probe(self):
        self._tick(50)
        self.assertEqual(len(self.supervisor.history()), 1)

    def test_history_is_bounded_under_flapping(self):
        for i in range(2000):
            ok = i % 2 == 0
            self.supervisor.observe(Probe(ok=ok, latency_ms=5.0, server_time=2000 + i), 1000 + i)
        self.assertLessEqual(len(self.supervisor.history()), 500)

    def test_availability_is_reported(self):
        self._tick(9)
        self.supervisor.observe(Probe(ok=False), 1100)
        self.assertAlmostEqual(self.supervisor.health.availability, 0.9, places=3)

    def test_the_summary_carries_a_code_beside_its_severity(self):
        """Colour never carries meaning alone anywhere in this application."""
        self._tick(3)
        summary = summarise(self.supervisor.health)
        self.assertEqual(summary.severity, "good")
        self.assertTrue(summary.code)
        self.assertIn("latency", summary.fields)


# ===========================================================================
class TestDataQuality(unittest.TestCase):
    def _series(self, count, period=300, start=100_000, skip_at=None):
        times, moment = [], start
        for i in range(count):
            if skip_at is not None and i == skip_at:
                moment += period * 4  # a hole
            else:
                moment += period
            times.append(moment)
        return times

    def test_a_full_clean_series_is_good(self):
        times = self._series(300)
        quality = inspect_series("EURUSD", Timeframe.M5, times, required=300, now=times[-1])
        self.assertEqual(quality.grade, Grade.GOOD)
        self.assertTrue(quality.usable)

    def test_no_bars_is_unusable(self):
        quality = inspect_series("EURUSD", Timeframe.M5, [], required=300, now=1000)
        self.assertEqual(quality.grade, Grade.UNUSABLE)

    def test_slightly_short_history_is_thin_not_unusable(self):
        times = self._series(250)
        quality = inspect_series("EURUSD", Timeframe.M5, times, required=300, now=times[-1])
        self.assertEqual(quality.grade, Grade.THIN)
        self.assertTrue(quality.usable)

    def test_badly_short_history_is_unusable(self):
        times = self._series(50)
        quality = inspect_series("EURUSD", Timeframe.M5, times, required=300, now=times[-1])
        self.assertEqual(quality.grade, Grade.UNUSABLE)

    def test_a_weekday_hole_is_a_gap(self):
        times = self._series(300, skip_at=150)
        quality = inspect_series("EURUSD", Timeframe.M5, times, required=300, now=times[-1])
        self.assertEqual(quality.grade, Grade.GAPPED)
        self.assertEqual(quality.gaps, 1)

    def test_a_weekend_is_not_a_gap(self):
        """The measure deliberately under-reports rather than crying wolf every
        Monday. A hole wider than the closure band is a market closure."""
        times = self._series(300)
        midpoint = len(times) // 2
        times = times[:midpoint] + [t + 300 * 600 for t in times[midpoint:]]
        quality = inspect_series("EURUSD", Timeframe.M5, times, required=300, now=times[-1])
        self.assertEqual(quality.gaps, 0)

    def test_an_old_newest_bar_is_stale(self):
        times = self._series(300)
        quality = inspect_series(
            "EURUSD", Timeframe.M5, times, required=300, now=times[-1] + 10_000
        )
        self.assertEqual(quality.grade, Grade.STALE)
        self.assertFalse(quality.usable)

    def test_one_bad_pass_is_not_chronic(self):
        monitor = DataQualityMonitor()
        bad = inspect_series("EURUSD", Timeframe.M5, [], required=300, now=1000)
        monitor.record("EURUSD", [bad], 1000)
        self.assertFalse(monitor.get("EURUSD").chronic)
        self.assertEqual(monitor.chronic(), [])

    def test_persistent_badness_becomes_chronic(self):
        """The pattern no per-pass message can ever state."""
        monitor = DataQualityMonitor()
        bad = inspect_series("EURUSD", Timeframe.M5, [], required=300, now=1000)
        for i in range(100):
            monitor.record("EURUSD", [bad], 1000 + i)
        record = monitor.get("EURUSD")
        self.assertTrue(record.chronic)
        self.assertEqual([r.symbol for r in monitor.chronic()], ["EURUSD"])

    def test_a_symbol_that_recovers_stops_being_chronic(self):
        monitor = DataQualityMonitor()
        bad = inspect_series("EURUSD", Timeframe.M5, [], required=300, now=1000)
        good_times = self._series(300)
        good = inspect_series(
            "EURUSD", Timeframe.M5, good_times, required=300, now=good_times[-1]
        )
        for i in range(20):
            monitor.record("EURUSD", [bad], 1000 + i)
        for i in range(200):
            monitor.record("EURUSD", [good], 2000 + i)
        self.assertFalse(monitor.get("EURUSD").chronic)

    def test_the_worst_timeframe_decides_the_symbol(self):
        monitor = DataQualityMonitor()
        good_times = self._series(300)
        good = inspect_series("EURUSD", Timeframe.M5, good_times, required=300, now=good_times[-1])
        bad = inspect_series("EURUSD", Timeframe.H1, [], required=300, now=1000)
        record = monitor.record("EURUSD", [good, bad], 1000)
        self.assertEqual(record.grade, Grade.UNUSABLE)

    def test_every_grade_has_a_severity_and_a_code(self):
        for grade in Grade:
            severity, code = severity_of(grade)
            self.assertIn(severity, {"good", "warning", "serious", "critical"})
            self.assertTrue(code)


# ===========================================================================
class TestOrderErrors(unittest.TestCase):
    def test_a_fill_is_not_a_failure(self):
        self.assertTrue(is_success(10009))
        self.assertEqual(classify(10009).category, ErrorCategory.NONE)

    def test_a_requote_is_retryable(self):
        error = classify(10004)
        self.assertEqual(error.category, ErrorCategory.MARKET)
        self.assertTrue(error.retryable)

    def test_invalid_stops_is_a_defect_and_never_retryable(self):
        """Sending an identical malformed request again fails identically
        forever. Saying so converts an infinite loop into one clear failure."""
        error = classify(10016)
        self.assertEqual(error.category, ErrorCategory.REQUEST)
        self.assertFalse(error.retryable)
        self.assertTrue(error.is_defect)

    def test_no_request_category_error_is_retryable(self):
        from alikhande.core.order_errors import _TABLE

        for error in _TABLE.values():
            if error.category == ErrorCategory.REQUEST:
                self.assertFalse(error.retryable, f"{error.code} is retryable")

    def test_an_unknown_retcode_is_unknown_and_not_retryable(self):
        """Defaulting an unrecognised rejection to retryable is how a build
        meets a new broker's custom code and spins."""
        error = classify(99999)
        self.assertEqual(error.category, ErrorCategory.UNKNOWN)
        self.assertFalse(error.retryable)
        self.assertIn("99999", error.code)

    def test_no_money_is_the_accounts_problem_not_a_defect(self):
        error = classify(10019)
        self.assertEqual(error.category, ErrorCategory.ACCOUNT)
        self.assertFalse(error.is_defect)

    def test_the_tally_ignores_successes(self):
        tally = ErrorTally()
        tally.record(10009, "EURUSD", 1000)
        self.assertEqual(tally.total(), 0)

    def test_the_tally_finds_the_pattern(self):
        """Forty INVALID_STOPS against one symbol says its stops level changed,
        and no per-order message ever says that."""
        tally = ErrorTally()
        for i in range(40):
            tally.record(10016, "XAUUSD", 1000 + i)
        tally.record(10004, "EURUSD", 2000)
        self.assertEqual(tally.total(), 41)
        self.assertEqual(tally.ranked()[0], ("INVALID_STOPS", 40))
        self.assertEqual(tally.defects(), {"INVALID_STOPS": 40})
        self.assertEqual(tally.last_symbol["INVALID_STOPS"], "XAUUSD")


# ===========================================================================
class TestRecovery(unittest.TestCase):
    def _record(self, **kwargs):
        base = dict(
            session_id="s1", environment="DEMO", version="2.2.0", started_at=1000
        )
        base.update(kwargs)
        return SessionRecord(**base)

    def test_a_first_run_is_not_a_crash(self):
        verdict = assess(None)
        self.assertEqual(verdict.kind, ExitKind.UNKNOWN)
        self.assertFalse(verdict.interrupt)

    def test_a_clean_exit_is_quiet(self):
        verdict = assess(self._record(closed_at=2000))
        self.assertEqual(verdict.kind, ExitKind.CLEAN)
        self.assertTrue(verdict.quiet)

    def test_a_missing_close_is_a_crash(self):
        verdict = assess(self._record(closed_at=0))
        self.assertEqual(verdict.kind, ExitKind.CRASH)
        self.assertTrue(verdict.interrupt)
        self.assertEqual(verdict.severity, "warning")

    def test_a_crash_holding_an_order_is_critical(self):
        """"The app died" and "the app died holding an order the broker may or
        may not have filled" are not the same news."""
        verdict = assess(
            self._record(closed_at=0, execution_in_flight=True, in_flight_symbol="XAUUSD")
        )
        self.assertEqual(verdict.severity, "critical")
        self.assertEqual(verdict.code, "RECOVERY_CRASH_WITH_UNRESOLVED")
        self.assertEqual(verdict.detail, "XAUUSD")

    def test_a_clean_exit_holding_an_order_still_interrupts(self):
        verdict = assess(self._record(closed_at=2000, execution_in_flight=True))
        self.assertTrue(verdict.interrupt)
        self.assertEqual(verdict.severity, "serious")

    def test_a_launch_does_not_assess_itself(self):
        """Assessing after appending would find a session with closed_at == 0
        and report a crash on every single start."""
        ledger = SessionLedger()
        verdict = ledger.open(self._record())
        self.assertEqual(verdict.kind, ExitKind.UNKNOWN)

    def test_a_crash_is_seen_by_the_next_launch(self):
        ledger = SessionLedger()
        ledger.open(self._record(session_id="s1"))
        # No close() — the process died.
        revived = SessionLedger(ledger.history())
        verdict = revived.open(self._record(session_id="s2", started_at=5000))
        self.assertEqual(verdict.kind, ExitKind.CRASH)
        self.assertEqual(verdict.previous.session_id, "s1")

    def test_a_clean_close_is_seen_by_the_next_launch(self):
        ledger = SessionLedger()
        ledger.open(self._record(session_id="s1"))
        ledger.close(4000)
        revived = SessionLedger(ledger.history())
        verdict = revived.open(self._record(session_id="s2", started_at=5000))
        self.assertEqual(verdict.kind, ExitKind.CLEAN)

    def test_the_in_flight_flag_is_written_during_the_session(self):
        """The flag's entire value is being correct at the moment the process
        dies, and a process that dies does not run its shutdown path."""
        ledger = SessionLedger()
        ledger.open(self._record())
        ledger.mark_in_flight("XAUUSD", True)
        revived = SessionLedger(ledger.history())
        verdict = revived.open(self._record(session_id="s2", started_at=5000))
        self.assertEqual(verdict.code, "RECOVERY_CRASH_WITH_UNRESOLVED")

    def test_history_is_bounded(self):
        ledger = SessionLedger()
        for i in range(400):
            ledger.open(self._record(session_id=f"s{i}", started_at=1000 + i))
            ledger.close(1000 + i + 1)
        self.assertLessEqual(len(ledger.history()), 50)

    def test_the_crashed_session_is_kept_not_overwritten(self):
        """A crash's evidence is written by the session that crashed, and
        overwriting it destroys the only record worth looking at."""
        ledger = SessionLedger()
        ledger.open(self._record(session_id="crashed"))
        revived = SessionLedger(ledger.history())
        revived.open(self._record(session_id="new", started_at=5000))
        ids = [s.session_id for s in revived.history()]
        self.assertIn("crashed", ids)


# ===========================================================================
class TestNotifications(unittest.TestCase):
    def setUp(self):
        self.router = NotificationRouter(minimum_urgency=Urgency.INFO)

    def test_a_notification_is_delivered(self):
        result = self.router.notify("signal.confirmed", "XAUUSD long", now=1000)
        self.assertIsNotNone(result)
        self.assertEqual(result.urgency, Urgency.NOTABLE)

    def test_a_repeat_within_the_window_is_throttled(self):
        self.router.notify("link.degraded", now=1000)
        self.assertIsNone(self.router.notify("link.degraded", now=1010))

    def test_throttling_is_per_subject_not_global(self):
        """A chatty subject must not crowd out a quiet, important one."""
        for i in range(40):
            self.router.notify("link.degraded", now=1000 + i)
        delivered = self.router.notify("execution.rejected", now=1005)
        self.assertIsNotNone(delivered)

    def test_critical_is_never_throttled(self):
        """An application that decides a repeated emergency has become
        background noise is worse than one that repeats itself."""
        for i in range(10):
            self.assertIsNotNone(self.router.notify("link.disconnected", now=1000 + i))

    def test_the_suppressed_count_survives_into_the_next_delivery(self):
        self.router.notify("link.degraded", now=1000)
        for i in range(5):
            self.router.notify("link.degraded", now=1001 + i)
        later = self.router.notify("link.degraded", now=1000 + 10_000)
        self.assertEqual(later.suppressed, 5)

    def test_below_the_minimum_urgency_nothing_is_delivered(self):
        router = NotificationRouter(minimum_urgency=Urgency.WARNING)
        self.assertIsNone(router.notify("signal.expired", now=1000))
        self.assertIsNotNone(router.notify("link.disconnected", now=1000))

    def test_every_known_subject_has_an_urgency(self):
        from alikhande.core.notifications import SUBJECTS

        for subject, urgency in SUBJECTS.items():
            self.assertIsInstance(urgency, Urgency, subject)

    def test_channels_escalate_rather_than_switch(self):
        """A critical event that only made a sound and left no row is one the
        operator cannot go back and read."""
        critical = self.router.notify("link.disconnected", now=1000)
        self.assertIn(Channel.PANEL, critical.channels)
        self.assertIn(Channel.TOAST, critical.channels)

    def test_an_info_notification_never_interrupts(self):
        info = self.router.notify("session.started", now=1000)
        self.assertFalse(info.interrupts)

    def test_the_panel_is_bounded(self):
        router = NotificationRouter(minimum_urgency=Urgency.INFO, capacity=20)
        for i in range(500):
            router.notify("link.disconnected", now=1000 + i)
        self.assertLessEqual(len(router.all()), 20)

    def test_muting_is_honoured_even_for_critical(self):
        """Muting is a deliberate act and the application should not overrule
        it — the UI marks it instead so the choice stays visible."""
        settings = NotificationSettings(muted={"link.disconnected"})
        notification = self.router.notify("link.disconnected", now=1000)
        self.assertFalse(settings.allows(notification))

    def test_disabling_sounds_removes_only_the_sound_channel(self):
        settings = NotificationSettings(toasts=True, sounds=False)
        critical = self.router.notify("link.disconnected", now=1000)
        channels = settings.channels_for(critical)
        self.assertIn(Channel.TOAST, channels)
        self.assertNotIn(Channel.SOUND, channels)

    def test_unread_counts_and_clears(self):
        self.router.notify("link.disconnected", now=1000)
        self.router.notify("execution.rejected", now=1001)
        self.assertEqual(self.router.unread, 2)
        self.router.mark_read()
        self.assertEqual(self.router.unread, 0)


# ===========================================================================
class TestMaintenance(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.database = self.root / "alikhande.sqlite"
        with sqlite3.connect(str(self.database)) as connection:
            connection.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY, symbol TEXT)")
            connection.executemany(
                "INSERT INTO signals (symbol) VALUES (?)", [("EURUSD",)] * 250
            )

    def tearDown(self):
        self._tmp.cleanup()

    # ---- backup ----------------------------------------------------------
    def test_a_backup_is_written_and_verified(self):
        result = backup_database(self.database, self.root / "backups")
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.verified)
        self.assertEqual(result.tables["signals"], 250)
        self.assertTrue(Path(result.path).exists())

    def test_a_backup_is_taken_from_a_database_being_written_to(self):
        """A shutil.copy of a live SQLite file produces a corrupt backup often
        enough to be useless and rarely enough to be trusted."""
        with sqlite3.connect(str(self.database)) as writer:
            writer.execute("INSERT INTO signals (symbol) VALUES ('XAUUSD')")
            result = backup_database(self.database, self.root / "backups")
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.verified)

    def test_backing_up_a_missing_database_fails_cleanly(self):
        result = backup_database(self.root / "nothing.sqlite", self.root / "backups")
        self.assertFalse(result.ok)
        self.assertIn("no database", result.error)

    def test_backups_are_listed_newest_first(self):
        import os
        import time

        first = backup_database(self.database, self.root / "backups", now=1_700_000_000)
        time.sleep(0.01)
        second = backup_database(self.database, self.root / "backups", now=1_700_000_060)
        os.utime(second.path, (time.time() + 10, time.time() + 10))
        listed = list_backups(self.root / "backups")
        self.assertEqual(listed[0].name, Path(second.path).name)
        self.assertEqual(len(listed), 2)
        self.assertTrue(first.ok)

    def test_pruning_never_drops_below_the_minimum(self):
        """A machine switched off for two months must not come back to an empty
        backup folder."""
        import os

        folder = self.root / "backups"
        for i in range(4):
            result = backup_database(self.database, folder, now=1_700_000_000 + i * 60)
            os.utime(result.path, (0, 0))  # ancient
        removed = prune_backups(folder, retention_days=1, keep_minimum=5)
        self.assertEqual(removed, [])
        self.assertEqual(len(list_backups(folder)), 4)

    def test_pruning_removes_the_genuinely_old_once_enough_remain(self):
        import os

        folder = self.root / "backups"
        for i in range(8):
            result = backup_database(self.database, folder, now=1_700_000_000 + i * 60)
            if i < 3:
                os.utime(result.path, (0, 0))
        removed = prune_backups(folder, retention_days=1, keep_minimum=5)
        self.assertEqual(len(removed), 3)

    # ---- restore ---------------------------------------------------------
    def test_a_restore_moves_the_current_file_aside(self):
        """Restoring the wrong file is a mistake an operator makes exactly once,
        at the worst possible moment, and it must be undoable."""
        backup = backup_database(self.database, self.root / "backups")
        with sqlite3.connect(str(self.database)) as connection:
            connection.execute("DELETE FROM signals")

        result = restore_database(backup.path, self.database)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(Path(result.displaced_to).exists())

        with sqlite3.connect(str(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 250)

    def test_a_corrupt_backup_is_refused_before_anything_is_moved(self):
        bad = self.root / "corrupt.sqlite"
        bad.write_bytes(b"this is not a database, it just has the right name")
        result = restore_database(bad, self.database)
        self.assertFalse(result.ok)
        self.assertEqual(result.displaced_to, "")
        self.assertTrue(self.database.exists())

    def test_restoring_a_missing_file_fails_cleanly(self):
        result = restore_database(self.root / "nope.sqlite", self.database)
        self.assertFalse(result.ok)

    # ---- settings --------------------------------------------------------
    def test_settings_round_trip(self):
        preferences = {"language": "fa", "theme": "dark", "environment": "DEMO"}
        path = export_settings(preferences, version="2.2.0", path=self.root / "settings.json")
        loaded, error = import_settings(path)
        self.assertEqual(error, "")
        self.assertEqual(loaded, preferences)

    def test_an_unknown_format_is_refused_rather_than_partly_applied(self):
        path = self.root / "future.json"
        path.write_text(
            json.dumps(
                {
                    "format": SETTINGS_FORMAT + 99,
                    "application": "AlikhandeScanner",
                    "preferences": {"language": "fa"},
                }
            ),
            encoding="utf-8",
        )
        loaded, error = import_settings(path)
        self.assertEqual(loaded, {})
        self.assertIn("cannot be read", error)

    def test_a_foreign_file_is_refused(self):
        path = self.root / "other.json"
        path.write_text(json.dumps({"application": "SomethingElse"}), encoding="utf-8")
        _, error = import_settings(path)
        self.assertIn("not an Alikhande", error)

    def test_unreadable_json_fails_cleanly(self):
        path = self.root / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        loaded, error = import_settings(path)
        self.assertEqual(loaded, {})
        self.assertTrue(error)

    # ---- diagnostics -----------------------------------------------------
    def test_the_bundle_names_the_build_and_the_machine(self):
        bundle = diagnostics(version="2.2.0", environment="DEMO", data_dir=self.root)
        self.assertEqual(bundle["application"]["version"], "2.2.0")
        self.assertEqual(bundle["application"]["environment"], "DEMO")
        self.assertIn("platform", bundle["machine"])

    def test_the_bundle_carries_no_credentials(self):
        class Account:
            login = 12345
            server = "Broker-Demo"
            is_demo = True
            currency = "USD"
            name = "Ali Khande"
            balance = 9_876.54
            password = "hunter2"

        bundle = diagnostics(
            version="2.2.0", environment="DEMO", data_dir=self.root, account=Account()
        )
        text = json.dumps(bundle)
        self.assertIn("12345", text)
        self.assertNotIn("hunter2", text)
        self.assertNotIn("Ali Khande", text)
        self.assertNotIn("9876.54", text)

    def test_the_bundle_serialises(self):
        supervisor = ConnectionSupervisor()
        supervisor.observe(Probe(ok=True, latency_ms=12.0, server_time=2000), 1000)
        monitor = DataQualityMonitor()
        monitor.record(
            "EURUSD",
            [inspect_series("EURUSD", Timeframe.M5, [], required=300, now=1000)],
            1000,
        )
        tally = ErrorTally()
        tally.record(10016, "XAUUSD", 1000)
        ledger = SessionLedger()
        ledger.open(SessionRecord(session_id="s1", environment="DEMO", started_at=1000))

        bundle = diagnostics(
            version="2.2.0",
            environment="DEMO",
            data_dir=self.root,
            link=supervisor.health,
            quality=monitor.symbols(),
            sessions=ledger.history(),
            errors=tally,
        )
        json.dumps(bundle)  # must not raise
        self.assertEqual(bundle["link"]["state"], "HEALTHY")
        self.assertIn("EURUSD", bundle["data_quality"])
        self.assertIn("INVALID_STOPS", bundle["order_errors"])


if __name__ == "__main__":
    unittest.main()
