"""The three environments and the production send lock.

These tests are adversarial by design. Most of them do not check that the
application works — they check that a specific bad thing is impossible, and
several are written as "try to break the lock and fail", because a safety
property nobody attacked is a safety property nobody has evidence for.
"""

from __future__ import annotations

import unittest

from alikhande.core import environment as env_module
from alikhande.core.enums import RunMode
from alikhande.core.environment import (
    PRODUCTION_LOCK_CODE,
    Capabilities,
    Environment,
    account_verdict,
    capabilities,
    coerce_mode,
    send_refusal,
)
from alikhande.core.execution import ExecutionEngine

# The broker stub and plan fixtures live in ``test_safety`` and are reused here
# rather than copied: a second copy drifts, and the copy that drifts is the one
# a safety test is asserting against. Two import forms because the suite is run
# both ways — ``unittest discover -s tests`` loads these as top-level modules,
# while ``alikhande selftest`` loads them as a package.
try:  # pragma: no cover - whichever form the runner used
    from .test_safety import StubGateway, demo_account, default_spec, valid_plan
except ImportError:  # pragma: no cover
    from test_safety import StubGateway, demo_account, default_spec, valid_plan


class TestCapabilityMatrix(unittest.TestCase):
    def test_every_environment_has_a_matrix(self):
        for name in Environment.ALL:
            self.assertIsInstance(capabilities(name), Capabilities)

    def test_only_demo_may_ever_send(self):
        """The whole point of the matrix, stated once."""
        self.assertTrue(capabilities(Environment.DEMO).may_send_orders)
        self.assertFalse(capabilities(Environment.PRODUCTION).may_send_orders)
        self.assertFalse(capabilities(Environment.BACKTEST).may_send_orders)

    def test_production_reports_the_lock_code(self):
        self.assertEqual(capabilities(Environment.PRODUCTION).send_lock, PRODUCTION_LOCK_CODE)

    def test_demo_confirm_is_unreachable_outside_demo(self):
        for name in (Environment.BACKTEST, Environment.PRODUCTION):
            self.assertNotIn(RunMode.DEMO_CONFIRM, capabilities(name).allowed_modes)

    def test_production_still_runs_everything_short_of_the_send(self):
        """Production readiness is measured, not assumed.

        If SHADOW were excluded, production would scan and stop — no sizing, no
        preflight, no reconciliation — and the readiness rehearsal the whole
        environment exists for would not happen.
        """
        caps = capabilities(Environment.PRODUCTION)
        self.assertIn(RunMode.SHADOW, caps.allowed_modes)
        self.assertEqual(caps.strongest_mode(), RunMode.SHADOW)
        self.assertTrue(caps.requires_live_gateway)
        self.assertTrue(caps.persistence_required)

    def test_each_environment_writes_its_own_database(self):
        stems = {capabilities(n).database_stem for n in Environment.ALL}
        self.assertEqual(len(stems), 3, "environments must not share a database file")

    def test_capabilities_are_frozen(self):
        caps = capabilities(Environment.PRODUCTION)
        with self.assertRaises(Exception):
            caps.may_send_orders = True  # type: ignore[misc]


class TestTheLockCannotBeOpened(unittest.TestCase):
    """Attacks on the lock. Each one should fail to unlock it."""

    def test_flipping_the_module_constant_does_not_unlock_production(self):
        """The constant exists to be asserted against, not to be a switch.

        ``capabilities`` hard-codes ``may_send_orders=False`` for production
        rather than deriving it from ``PRODUCTION_SEND_LOCK``, so somebody who
        finds the constant and flips it has changed nothing.
        """
        original = env_module.PRODUCTION_SEND_LOCK
        try:
            env_module.PRODUCTION_SEND_LOCK = False
            self.assertFalse(capabilities(Environment.PRODUCTION).may_send_orders)
            self.assertEqual(
                capabilities(Environment.PRODUCTION).send_lock, PRODUCTION_LOCK_CODE
            )
        finally:
            env_module.PRODUCTION_SEND_LOCK = original

    def test_an_unknown_environment_falls_back_to_demo_not_production(self):
        """A typo must land somewhere restricted, never somewhere consequential."""
        self.assertEqual(Environment.parse("prodution"), Environment.DEMO)
        self.assertEqual(Environment.parse(None), Environment.DEMO)
        self.assertEqual(Environment.parse(42), Environment.DEMO)

    def test_no_environment_name_produces_a_sendable_production(self):
        """Case variants and whitespace must not route around the matrix."""
        for candidate in ("PRODUCTION", "production", "Production", "PrOdUcTiOn"):
            caps = capabilities(candidate)
            if caps.environment == Environment.PRODUCTION:
                self.assertFalse(caps.may_send_orders)

    def test_send_refusal_refuses_every_mode_in_production(self):
        for mode in RunMode:
            self.assertNotEqual(
                send_refusal(Environment.PRODUCTION, mode),
                "",
                f"{mode.name} found an opening in production",
            )

    def test_send_refusal_refuses_every_mode_in_backtest(self):
        for mode in RunMode:
            self.assertNotEqual(send_refusal(Environment.BACKTEST, mode), "")

    def test_demo_confirm_is_the_only_combination_that_clears(self):
        cleared = [
            (name, mode)
            for name in Environment.ALL
            for mode in RunMode
            if send_refusal(name, mode) == ""
        ]
        self.assertEqual(cleared, [(Environment.DEMO, RunMode.DEMO_CONFIRM)])


class TestEngineHonoursTheEnvironment(unittest.TestCase):
    """The lock as the execution engine actually applies it.

    A **demo** account is used throughout, deliberately. The existing
    ``REAL_ACCOUNT_BLOCKED`` check would refuse a real one on its own, and a
    test that fed it a real account would prove nothing about *this* layer. The
    point is that production refuses in exactly the case where every other
    check would have let the order through.
    """

    def setUp(self):
        self.gateway = StubGateway()
        self.plan = valid_plan(now=1000)

    def _engine(self, environment: str) -> ExecutionEngine:
        return ExecutionEngine(environment=environment)

    def _submit(self, environment: str, mode: RunMode, engine: ExecutionEngine | None = None):
        engine = engine or self._engine(environment)
        return engine.submit(
            self.plan,
            mode,
            gateway=self.gateway,
            account=demo_account(),
            spec=default_spec("EURUSD"),
            now=1000,
        )

    def test_production_refuses_demo_confirm_on_a_demo_account(self):
        ok, reason = self._submit(Environment.PRODUCTION, RunMode.DEMO_CONFIRM)
        self.assertFalse(ok)
        self.assertEqual(reason, "MODE_NOT_AVAILABLE_IN_PRODUCTION")
        self.assertEqual(self.gateway.sent, [])

    def test_backtest_refuses_demo_confirm_on_a_demo_account(self):
        ok, reason = self._submit(Environment.BACKTEST, RunMode.DEMO_CONFIRM)
        self.assertFalse(ok)
        self.assertEqual(reason, "MODE_NOT_AVAILABLE_IN_BACKTEST")
        self.assertEqual(self.gateway.sent, [])

    def test_production_shadow_runs_the_full_path_and_sends_nothing(self):
        ok, reason = self._submit(Environment.PRODUCTION, RunMode.SHADOW)
        self.assertTrue(ok, f"production shadow should complete, got {reason}")
        self.assertEqual(reason, "SHADOW_MODE")
        self.assertEqual(self.gateway.sent, [])

    def test_demo_confirm_in_the_demo_environment_still_sends(self):
        """The control. Without this, every test above would pass on a build
        that had simply broken execution altogether."""
        ok, reason = self._submit(Environment.DEMO, RunMode.DEMO_CONFIRM)
        self.assertTrue(ok, reason)
        self.assertEqual(len(self.gateway.sent), 1)

    def test_the_send_gate_holds_when_the_environment_changes_mid_flight(self):
        """Defence in depth *within* the method.

        The mode check at the top of ``submit`` is one line, and one line is
        one edit away from being gone. This reaches past it: the engine accepts
        DEMO_CONFIRM as a demo engine, and the environment is switched to
        production while preflight is running. The second gate, immediately
        before ``send_order``, must still refuse.
        """
        engine = self._engine(Environment.DEMO)
        real_preflight = engine._preflight.validate

        def flip_then_validate(*args, **kwargs):
            engine.set_environment(Environment.PRODUCTION)
            return real_preflight(*args, **kwargs)

        engine._preflight.validate = flip_then_validate  # type: ignore[method-assign]

        ok, reason = self._submit(Environment.DEMO, RunMode.DEMO_CONFIRM, engine=engine)
        self.assertFalse(ok)
        self.assertEqual(reason, PRODUCTION_LOCK_CODE)
        self.assertEqual(self.gateway.sent, [], "an order left under the production lock")

    def test_a_blocked_send_is_recorded_not_silently_dropped(self):
        engine = self._engine(Environment.DEMO)
        real_preflight = engine._preflight.validate

        def flip_then_validate(*args, **kwargs):
            engine.set_environment(Environment.PRODUCTION)
            return real_preflight(*args, **kwargs)

        engine._preflight.validate = flip_then_validate  # type: ignore[method-assign]
        self._submit(Environment.DEMO, RunMode.DEMO_CONFIRM, engine=engine)

        self.assertEqual(engine.current.message, PRODUCTION_LOCK_CODE)
        self.assertTrue(engine.current.terminal, "a refused send must not stay in flight")

    def test_the_engine_defaults_to_demo(self):
        """This build has always been the demo build. Declaring the environment
        must not have silently changed what an unconfigured engine does."""
        self.assertEqual(ExecutionEngine().environment, Environment.DEMO)


class TestModeCoercion(unittest.TestCase):
    def test_demo_confirm_clamps_down_when_entering_production(self):
        mode, reason = coerce_mode(Environment.PRODUCTION, RunMode.DEMO_CONFIRM)
        self.assertEqual(mode, RunMode.SHADOW)
        self.assertEqual(reason, "MODE_NOT_AVAILABLE_IN_PRODUCTION")

    def test_an_allowed_mode_passes_through_unchanged_and_silent(self):
        mode, reason = coerce_mode(Environment.DEMO, RunMode.DEMO_CONFIRM)
        self.assertEqual(mode, RunMode.DEMO_CONFIRM)
        self.assertEqual(reason, "")

    def test_coercion_never_promotes(self):
        """Clamping is downward only. Nothing may gain capability by switching
        environments."""
        for name in Environment.ALL:
            for mode in RunMode:
                coerced, _ = coerce_mode(name, mode)
                self.assertLessEqual(int(coerced), int(mode))


class TestAccountVerdict(unittest.TestCase):
    def test_a_real_account_in_the_demo_environment_is_critical(self):
        severity, code = account_verdict(Environment.DEMO, is_demo=False)
        self.assertEqual(severity, "critical")
        self.assertEqual(code, "REAL_ACCOUNT_IN_DEMO_ENVIRONMENT")

    def test_a_demo_account_in_production_is_only_a_warning(self):
        """It wastes the rehearsal. It does not risk anything."""
        severity, _ = account_verdict(Environment.PRODUCTION, is_demo=True)
        self.assertEqual(severity, "warning")

    def test_matching_accounts_are_good(self):
        self.assertEqual(account_verdict(Environment.DEMO, True)[0], "good")
        self.assertEqual(account_verdict(Environment.PRODUCTION, False)[0], "good")

    def test_an_unknown_account_is_unknown_not_good(self):
        """"Nobody looked" must never render as "fine"."""
        severity, _ = account_verdict(Environment.DEMO, is_demo=None)
        self.assertEqual(severity, "unknown")


if __name__ == "__main__":
    unittest.main()
