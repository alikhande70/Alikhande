"""The robot, and the line it must not cross.

The first class here is the important one. Everything else tests that the
automation is useful; ``TestTheRobotNeverExecutes`` tests that it is safe, and
that no combination of policy, environment or state gets it to act on the
operator's behalf where judgement is required.
"""

from __future__ import annotations

import unittest

from alikhande.core.environment import Environment
from alikhande.core.robot import (
    AUTO_EXECUTE_LOCK,
    DEFAULT_WINDOWS,
    PAUSE_REVIEW_SECONDS,
    HoldReason,
    Robot,
    RobotPolicy,
    RobotState,
    SessionWindow,
    minute_of_day,
)

MONDAY = 0
SATURDAY = 5


def watching_policy(**kwargs) -> RobotPolicy:
    defaults = dict(
        enabled=True,
        windows=(SessionWindow("test", 0, 24 * 60),),
    )
    defaults.update(kwargs)
    return RobotPolicy(**defaults)


def clear(**kwargs):
    """Arguments to ``evaluate`` describing a completely healthy pass."""
    base = dict(
        now=1_700_000_000,
        weekday=MONDAY,
        minute_of_day=10 * 60,
        environment=Environment.DEMO,
        link_usable=True,
        data_usable=True,
        news_blocked=False,
        may_trade=True,
        execution_unresolved=False,
        candidates=3,
    )
    base.update(kwargs)
    return base


# ===========================================================================
class TestTheRobotNeverExecutes(unittest.TestCase):
    """Two deliberate human actions on separate controls. A robot that
    performed either one would not weaken that gate — it would remove it."""

    def test_the_decision_has_no_arm_or_confirm_field(self):
        """Structural. The robot cannot instruct an arm because there is
        nowhere in its output to say so."""
        decision = Robot(watching_policy()).evaluate(**clear())
        for forbidden in ("arm", "confirm", "submit", "send", "execute"):
            self.assertFalse(
                hasattr(decision, forbidden),
                f"RobotDecision grew a `{forbidden}` field",
            )

    def test_may_execute_is_locked_in_every_environment(self):
        for name in Environment.ALL:
            policy = watching_policy()
            allowed, reason = policy.may_execute()
            self.assertFalse(allowed, name)
            self.assertEqual(reason, AUTO_EXECUTE_LOCK)

    def test_requesting_auto_execute_changes_nothing(self):
        """The field exists so the UI can show the capability and its lock.
        `may_execute` never consults it."""
        policy = watching_policy(auto_execute_requested=True)
        allowed, reason = policy.may_execute()
        self.assertFalse(allowed)
        self.assertEqual(reason, AUTO_EXECUTE_LOCK)

    def test_a_fully_permissive_policy_still_only_watches(self):
        policy = RobotPolicy(
            enabled=True,
            windows=(SessionWindow("always", 0, 24 * 60),),
            auto_reconnect=True,
            auto_disarm=True,
            auto_pause_on_guard=False,
            auto_pause_on_degradation=False,
            auto_backup=True,
            auto_execute_requested=True,
            minimum_score=0.0,
        )
        decision = Robot(policy).evaluate(**clear(candidates=99))
        self.assertEqual(decision.status.state, RobotState.WATCHING)
        self.assertIn("PRESENT", decision.status.actions)
        self.assertNotIn("ARM", decision.status.actions)
        self.assertNotIn("CONFIRM", decision.status.actions)

    def test_disarming_is_allowed_because_it_reduces_exposure(self):
        """The asymmetry is the design: actions that create exposure need
        ceremony, actions that remove it do not."""
        decision = Robot(watching_policy()).evaluate(**clear(armed_stale=True))
        self.assertTrue(decision.disarm)


# ===========================================================================
class TestSessionWindows(unittest.TestCase):
    def test_a_plain_window_contains_its_own_hours(self):
        window = SessionWindow("london", 7 * 60, 16 * 60)
        self.assertTrue(window.contains(MONDAY, 9 * 60))
        self.assertFalse(window.contains(MONDAY, 6 * 60))
        self.assertFalse(window.contains(MONDAY, 17 * 60))

    def test_the_end_minute_is_exclusive(self):
        window = SessionWindow("london", 7 * 60, 16 * 60)
        self.assertFalse(window.contains(MONDAY, 16 * 60))
        self.assertTrue(window.contains(MONDAY, 16 * 60 - 1))

    def test_a_window_can_wrap_midnight(self):
        """Asia. Expressible as start > end rather than as two rows the
        operator has to keep in sync."""
        window = SessionWindow("asia", 23 * 60, 8 * 60)
        self.assertTrue(window.contains(MONDAY, 23 * 60 + 30))
        self.assertTrue(window.contains(MONDAY, 2 * 60))
        self.assertFalse(window.contains(MONDAY, 12 * 60))

    def test_day_filters_apply(self):
        window = SessionWindow("weekdays", 0, 24 * 60, days=(0, 1, 2, 3, 4))
        self.assertTrue(window.contains(MONDAY, 12 * 60))
        self.assertFalse(window.contains(SATURDAY, 12 * 60))

    def test_a_disabled_window_contains_nothing(self):
        window = SessionWindow("off", 0, 24 * 60, enabled=False)
        self.assertFalse(window.contains(MONDAY, 12 * 60))

    def test_the_defaults_cover_london_and_new_york_on_weekdays(self):
        robot = Robot(RobotPolicy(enabled=True, windows=DEFAULT_WINDOWS))
        self.assertIsNotNone(robot.active_window(MONDAY, 9 * 60))
        self.assertIsNotNone(robot.active_window(MONDAY, 18 * 60))
        self.assertIsNone(robot.active_window(SATURDAY, 9 * 60))

    def test_the_next_window_is_found_across_a_weekend(self):
        robot = Robot(RobotPolicy(enabled=True, windows=DEFAULT_WINDOWS))
        name, minutes = robot.next_window(SATURDAY, 12 * 60)
        self.assertEqual(name, "london")
        self.assertGreater(minutes, 0)

    def test_no_enabled_windows_yields_no_next(self):
        robot = Robot(RobotPolicy(enabled=True, windows=(SessionWindow("x", 0, 60, enabled=False),)))
        self.assertEqual(robot.next_window(MONDAY, 0), ("", 0))

    def test_minute_of_day_uses_utc_not_local(self):
        """Applying a local timezone would shift every window by whatever the
        operator's machine is set to."""
        weekday, minute = minute_of_day(0)  # 1970-01-01T00:00Z, a Thursday
        self.assertEqual(weekday, 3)
        self.assertEqual(minute, 0)


# ===========================================================================
class TestRobotLifecycle(unittest.TestCase):
    def test_a_disabled_robot_is_stopped_and_does_nothing(self):
        decision = Robot(RobotPolicy(enabled=False)).evaluate(**clear())
        self.assertEqual(decision.status.state, RobotState.STOPPED)
        self.assertFalse(decision.backup)
        self.assertFalse(decision.reconnect)

    def test_outside_every_window_it_idles(self):
        robot = Robot(RobotPolicy(enabled=True, windows=DEFAULT_WINDOWS))
        decision = robot.evaluate(**clear(weekday=SATURDAY))
        self.assertEqual(decision.status.state, RobotState.IDLE)
        self.assertEqual(decision.status.hold, HoldReason.OUTSIDE_WINDOW)

    def test_inside_a_window_and_healthy_it_watches(self):
        decision = Robot(watching_policy()).evaluate(**clear())
        self.assertEqual(decision.status.state, RobotState.WATCHING)
        self.assertEqual(decision.status.candidates, 3)
        self.assertEqual(decision.status.severity, "good")

    def test_maintenance_runs_outside_windows_too(self):
        """A machine that only ever runs overnight would otherwise never get a
        backup."""
        robot = Robot(RobotPolicy(enabled=True, windows=DEFAULT_WINDOWS, auto_backup=True))
        decision = robot.evaluate(**clear(weekday=SATURDAY))
        self.assertEqual(decision.status.state, RobotState.IDLE)
        self.assertTrue(decision.backup)

    def test_a_backup_is_not_taken_again_within_the_interval(self):
        robot = Robot(watching_policy(auto_backup=True, backup_interval_hours=12))
        first = robot.evaluate(**clear(now=1_700_000_000))
        self.assertTrue(first.backup)
        second = robot.evaluate(**clear(now=1_700_000_000 + 3600))
        self.assertFalse(second.backup)
        later = robot.evaluate(**clear(now=1_700_000_000 + 13 * 3600))
        self.assertTrue(later.backup)

    def test_reconnection_is_requested_outside_windows(self):
        """A link that is down outside a window must be back up before the next
        one opens."""
        robot = Robot(RobotPolicy(enabled=True, windows=DEFAULT_WINDOWS, auto_reconnect=True))
        decision = robot.evaluate(**clear(weekday=SATURDAY, link_usable=False))
        self.assertTrue(decision.reconnect)


# ===========================================================================
class TestHolding(unittest.TestCase):
    def _hold(self, **kwargs):
        policy = watching_policy(auto_pause_on_guard=False, auto_pause_on_degradation=False)
        return Robot(policy).evaluate(**clear(**kwargs))

    def test_a_risk_guard_holds(self):
        decision = self._hold(may_trade=False)
        self.assertEqual(decision.status.hold, HoldReason.RISK_GUARD)

    def test_an_unresolved_execution_holds(self):
        decision = self._hold(execution_unresolved=True)
        self.assertEqual(decision.status.hold, HoldReason.EXECUTION_UNRESOLVED)

    def test_unusable_data_holds(self):
        decision = self._hold(data_usable=False)
        self.assertEqual(decision.status.hold, HoldReason.DATA_UNUSABLE)

    def test_news_holds_where_the_environment_says_it_should(self):
        decision = self._hold(news_blocked=True, environment=Environment.DEMO)
        self.assertEqual(decision.status.hold, HoldReason.NEWS_BLOCKED)

    def test_news_does_not_hold_a_backtest(self):
        """There is no live calendar to consult for bars recorded last year,
        and blocking on that would make every replay empty."""
        decision = self._hold(news_blocked=True, environment=Environment.BACKTEST)
        self.assertNotEqual(decision.status.hold, HoldReason.NEWS_BLOCKED)

    def test_the_worst_reason_is_the_one_reported(self):
        """An operator told "data unusable" while a risk guard is tripped has
        been told the least useful true thing available."""
        decision = self._hold(
            may_trade=False, data_usable=False, news_blocked=True, execution_unresolved=True
        )
        self.assertEqual(decision.status.hold, HoldReason.EXECUTION_UNRESOLVED)


# ===========================================================================
class TestPausing(unittest.TestCase):
    def test_a_tripped_guard_pauses_the_robot(self):
        robot = Robot(watching_policy(auto_pause_on_guard=True))
        decision = robot.evaluate(**clear(may_trade=False))
        self.assertEqual(decision.status.state, RobotState.PAUSED)
        self.assertGreater(decision.status.paused_until, 0)

    def test_a_pause_notifies_once_not_every_pass(self):
        robot = Robot(watching_policy(auto_pause_on_guard=True))
        first = robot.evaluate(**clear(now=1000, may_trade=False))
        self.assertIn(("robot.paused", "RISK_GUARD"), first.notify)
        second = robot.evaluate(**clear(now=1001, may_trade=False))
        self.assertEqual(second.notify, ())

    def test_a_pause_expires_and_re_evaluates(self):
        """A robot that stayed paused until somebody noticed would be a robot
        that stopped."""
        robot = Robot(watching_policy(auto_pause_on_guard=True))
        robot.evaluate(**clear(now=1000, may_trade=False))
        recovered = robot.evaluate(**clear(now=1000 + PAUSE_REVIEW_SECONDS + 1))
        self.assertEqual(recovered.status.state, RobotState.WATCHING)
        self.assertIn("PAUSE_EXPIRED", recovered.status.actions)

    def test_resuming_clears_a_pause_immediately(self):
        robot = Robot(watching_policy(auto_pause_on_guard=True))
        robot.evaluate(**clear(now=1000, may_trade=False))
        robot.resume()
        decision = robot.evaluate(**clear(now=1001))
        self.assertEqual(decision.status.state, RobotState.WATCHING)

    def test_maintenance_still_runs_while_paused(self):
        """A paused robot is not a stopped one. The link still needs to come
        back and the database still needs backing up."""
        robot = Robot(watching_policy(auto_pause_on_guard=True, auto_reconnect=True))
        robot.evaluate(**clear(now=1000, may_trade=False))
        decision = robot.evaluate(**clear(now=1002, may_trade=False, link_usable=False))
        self.assertEqual(decision.status.state, RobotState.PAUSED)
        self.assertTrue(decision.reconnect)

    def test_resuming_from_a_hold_notifies(self):
        robot = Robot(watching_policy(auto_pause_on_guard=False, auto_pause_on_degradation=False))
        robot.evaluate(**clear(now=1000, may_trade=False))
        decision = robot.evaluate(**clear(now=1001))
        self.assertIn(("robot.resumed", "test"), decision.notify)

    def test_stop_clears_everything(self):
        robot = Robot(watching_policy(auto_pause_on_guard=True))
        robot.evaluate(**clear(may_trade=False))
        robot.stop()
        self.assertEqual(robot.status.state, RobotState.STOPPED)

    def test_degradation_pausing_can_be_turned_off_independently(self):
        robot = Robot(watching_policy(auto_pause_on_guard=True, auto_pause_on_degradation=False))
        decision = robot.evaluate(**clear(data_usable=False))
        self.assertEqual(decision.status.state, RobotState.HOLDING)


if __name__ == "__main__":
    unittest.main()
