"""Do the subsystems actually reach the product?

Every module in ``core`` had its own passing tests. Four of them were
nevertheless dead: the order-error taxonomy was fed by nothing, the robot's
reconnect and disarm decisions were returned and discarded, notifications were
routed into a deque nobody read, and the crash-recovery verdict was computed at
startup and thrown away.

Unit tests cannot catch that, by construction — a module with no consumers
passes its own tests perfectly. So these are *coupling* tests. Each one asserts
that a decision made in one place produces an effect in another, which is the
only property that was actually missing.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from alikhande.core.enums import RunMode
from alikhande.core.environment import Environment
from alikhande.core.execution import ExecutionEngine
from alikhande.core.journal import Journal
from alikhande.core.models import OrderResult
from alikhande.core.notifications import NotificationRouter, Urgency
from alikhande.core.recovery import SessionLedger, SessionRecord, assess
from alikhande.core.robot import Robot, RobotPolicy, SessionWindow

try:  # pragma: no cover - depends on how the suite was launched
    from .test_safety import StubGateway, demo_account, default_spec, valid_plan
except ImportError:  # pragma: no cover
    from test_safety import StubGateway, demo_account, default_spec, valid_plan


# ===========================================================================
class TestOrderErrorsAreRecorded(unittest.TestCase):
    """The taxonomy classified retcodes beautifully and was called by nothing.

    Every diagnostics bundle reported zero order errors no matter how many the
    broker had refused.
    """

    def _reject_with(self, retcode: int):
        journal = Journal()
        engine = ExecutionEngine(journal=journal, environment=Environment.DEMO)
        gateway = StubGateway()
        gateway.result = OrderResult(
            ok=False, retcode=retcode, comment="rejected", volume=0.0, price=0.0
        )
        ok, reason = engine.submit(
            valid_plan(now=1000),
            RunMode.DEMO_CONFIRM,
            gateway=gateway,
            account=demo_account(),
            spec=default_spec("EURUSD"),
            now=1000,
        )
        return engine, journal, ok, reason

    def test_a_rejection_lands_in_the_tally(self):
        engine, _journal, ok, _reason = self._reject_with(10016)
        self.assertFalse(ok)
        self.assertEqual(engine.errors.total(), 1)
        self.assertEqual(engine.errors.ranked()[0][0], "INVALID_STOPS")

    def test_the_reason_carries_the_classified_name_not_a_bare_number(self):
        """`ORDER_SEND_FAILED(10016:...)` tells the operator nothing. The code
        name is the smallest thing that is actually a diagnosis."""
        _engine, _journal, _ok, reason = self._reject_with(10016)
        self.assertIn("INVALID_STOPS", reason)

    def test_a_request_defect_is_journalled_as_this_builds_fault(self):
        """INVALID_STOPS means this application constructed an invalid order.
        That is not something to hand the operator as "try again"."""
        _engine, journal, _ok, _reason = self._reject_with(10016)
        codes = [e.code for e in journal.entries()]
        self.assertIn("ORDER_REQUEST_DEFECT", codes)

    def test_a_market_rejection_is_not_reported_as_a_defect(self):
        _engine, journal, _ok, _reason = self._reject_with(10004)  # REQUOTE
        codes = [e.code for e in journal.entries()]
        self.assertNotIn("ORDER_REQUEST_DEFECT", codes)

    def test_the_tally_separates_defects_from_the_market(self):
        engine = ExecutionEngine(environment=Environment.DEMO)
        engine.errors.record(10016, "XAUUSD", 1000)  # our fault
        engine.errors.record(10004, "EURUSD", 1001)  # the market
        self.assertEqual(engine.errors.defects(), {"INVALID_STOPS": 1})
        self.assertEqual(engine.errors.total(), 2)

    def test_an_accepted_order_adds_nothing_to_the_tally(self):
        journal = Journal()
        engine = ExecutionEngine(journal=journal, environment=Environment.DEMO)
        gateway = StubGateway()
        ok, _ = engine.submit(
            valid_plan(now=1000),
            RunMode.DEMO_CONFIRM,
            gateway=gateway,
            account=demo_account(),
            spec=default_spec("EURUSD"),
            now=1000,
        )
        self.assertTrue(ok)
        self.assertEqual(engine.errors.total(), 0)

    def test_an_unknown_retcode_is_tallied_under_its_own_name(self):
        engine, _journal, _ok, _reason = self._reject_with(99999)
        self.assertEqual(engine.errors.total(), 1)
        self.assertIn("UNKNOWN_99999", dict(engine.errors.ranked()))


# ===========================================================================
class TestRobotDecisionsAreActedOn(unittest.TestCase):
    """The robot decides; something else must act.

    That split keeps the robot testable, and it is worth nothing if the acting
    half does not exist — which for `reconnect` and `disarm` it did not, making
    two checkboxes in the Robot view purely decorative.
    """

    def _decision(self, **kwargs):
        policy = RobotPolicy(
            enabled=True,
            windows=(SessionWindow("test", 0, 24 * 60),),
            auto_reconnect=True,
            auto_disarm=True,
        )
        base = dict(
            now=1_700_000_000,
            weekday=0,
            minute_of_day=600,
            environment=Environment.DEMO,
            link_usable=True,
            data_usable=True,
            news_blocked=False,
            may_trade=True,
            execution_unresolved=False,
            candidates=0,
        )
        base.update(kwargs)
        return Robot(policy).evaluate(**base)

    def test_every_field_of_a_decision_is_read_by_the_window(self):
        """A guard against the decision growing a field the app forgets to
        read — which is exactly how reconnect and disarm ended up ignored.

        Reads the source rather than the behaviour on purpose. The behavioural
        version would need a live window, a broken link and a stale intent all
        at once; this catches the same omission at the moment it is introduced.
        """
        import dataclasses
        import inspect

        from alikhande.core.robot import RobotDecision
        from alikhande.ui import main_window

        body = inspect.getsource(main_window.MainWindow._drive_robot)
        for field in dataclasses.fields(RobotDecision):
            if field.name == "status":
                continue  # rendered, not acted on
            self.assertIn(
                f"decision.{field.name}",
                body,
                f"the robot can ask for `{field.name}` and _drive_robot never reads it",
            )

    def test_an_unusable_link_asks_for_a_reconnect(self):
        self.assertTrue(self._decision(link_usable=False).reconnect)

    def test_a_stale_armed_intent_asks_for_a_disarm(self):
        self.assertTrue(self._decision(armed_stale=True).disarm)

    def test_a_healthy_pass_asks_for_neither(self):
        decision = self._decision()
        self.assertFalse(decision.reconnect)
        self.assertFalse(decision.disarm)


# ===========================================================================
class TestNotificationsReachSomewhere(unittest.TestCase):
    def test_the_router_hands_survivors_to_its_delivery(self):
        delivered = []
        router = NotificationRouter(
            minimum_urgency=Urgency.INFO, delivery=delivered.append
        )
        router.notify("link.disconnected", "gone", now=1000)
        self.assertEqual(len(delivered), 1)

    def test_a_throttled_notification_is_not_delivered_twice(self):
        delivered = []
        router = NotificationRouter(
            minimum_urgency=Urgency.INFO, delivery=delivered.append
        )
        router.notify("link.degraded", now=1000)
        router.notify("link.degraded", now=1001)
        self.assertEqual(len(delivered), 1)

    def test_every_subject_the_window_raises_has_a_title_key(self):
        """A notification whose title renders as `notify.link.stalled` is a
        notification nobody can read."""
        import inspect
        import re

        from alikhande.i18n import EN
        from alikhande.ui import main_window

        source = inspect.getsource(main_window)
        raised = set(re.findall(r'_notify\(\s*"([a-z_.]+)"', source))
        raised |= set(re.findall(r'notify\.append\(\("([a-z_.]+)"', source))
        self.assertTrue(raised, "no notification subjects found to check")
        for subject in raised:
            self.assertIn(
                f"notify.{subject}",
                EN,
                f"{subject} is raised but has no English title",
            )


# ===========================================================================
class TestRecoveryVerdictIsUsed(unittest.TestCase):
    def _record(self, **kwargs):
        base = dict(session_id="s1", environment="DEMO", version="2.2.0", started_at=1000)
        base.update(kwargs)
        return SessionRecord(**base)

    def test_a_clean_exit_produces_a_quiet_verdict(self):
        ledger = SessionLedger()
        ledger.open(self._record(session_id="s1"))
        ledger.close(2000)
        revived = SessionLedger(ledger.history())
        self.assertTrue(revived.open(self._record(session_id="s2", started_at=3000)).quiet)

    def test_every_verdict_code_has_a_translation(self):
        """The verdict is rendered by looking up `recovery.<code>`. A code with
        no entry renders as its own key, which is how a critical warning turns
        into `recovery.recovery_crash_with_unresolved` on screen."""
        from alikhande.i18n import EN, FA

        for previous in (
            None,
            self._record(closed_at=2000),
            self._record(closed_at=0),
            self._record(closed_at=0, execution_in_flight=True),
            self._record(closed_at=2000, execution_in_flight=True),
        ):
            code = assess(previous).code
            key = f"recovery.{code.lower()}"
            self.assertIn(key, EN, f"{code} has no English text")
            self.assertIn(key, FA, f"{code} has no Persian text")

    def test_the_window_reports_the_verdict_at_launch(self):
        import inspect

        from alikhande.ui import main_window

        body = inspect.getsource(main_window.MainWindow.__init__)
        self.assertIn(
            "_report_recovery",
            body,
            "the recovery verdict is computed at startup and never reported",
        )


if __name__ == "__main__":
    unittest.main()
