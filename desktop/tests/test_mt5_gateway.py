"""The MT5 adapter, executed.

Every test here runs the real ``adapters/mt5/gateway.py`` against a module
double. Before this file existed, that module had never executed at all, and
the cost of that was a defect which broke every live pass while the suite
stayed green.

``TestThreadOwnership`` is the one that matters most. It is written as the
application actually behaves — attach somewhere, call from somewhere else — and
it fails against the code as it was.
"""

from __future__ import annotations

import threading
import unittest

from alikhande.core.enums import Direction, Timeframe
from alikhande.core.models import OrderRequest
from alikhande.core.ports import GatewayError

try:  # pragma: no cover - depends on how the suite was launched
    from .fake_mt5 import ORDER_FILLING_IOC, FakeAccount, FakeMT5, install, uninstall
except ImportError:  # pragma: no cover
    from fake_mt5 import ORDER_FILLING_IOC, FakeAccount, FakeMT5, install, uninstall


class MT5TestCase(unittest.TestCase):
    def setUp(self):
        self.mt5 = install(FakeMT5())
        # Import after installing, and reload, so the adapter's `_import_mt5`
        # picks up the double rather than a cached real module.
        from alikhande.adapters.mt5 import gateway as gateway_module

        self.module = gateway_module
        self.gateway = gateway_module.MT5Gateway()

    def tearDown(self):
        try:
            self.gateway.shutdown()
        except Exception:
            pass
        uninstall()


# ===========================================================================
class TestThreadOwnership(MT5TestCase):
    """The defect that broke every live pass.

    The MetaTrader5 package holds process-global connection state and the
    adapter stamps an owner thread on attach. The application attaches on one
    thread (the UI) and calls from another (the scan worker), so unless the
    attachment happens on the calling thread, every call raises — silently,
    because the engine swallows gateway errors and reports "not connected".
    """

    def test_connecting_on_one_thread_and_calling_from_another_is_refused(self):
        """The original bug, reproduced. This is a property of the guard and it
        is correct — the fix is to connect on the right thread, not to weaken
        this."""
        self.gateway.connect()
        captured = {}

        def call_from_elsewhere():
            try:
                self.gateway.symbols()
            except GatewayError as error:
                captured["error"] = str(error)

        thread = threading.Thread(target=call_from_elsewhere)
        thread.start()
        thread.join()
        self.assertIn("thread other than", captured.get("error", ""))

    def test_ensure_connected_attaches_on_the_calling_thread(self):
        """What the worker now does, and the whole point of the fix."""
        captured = {}

        def worker():
            try:
                self.gateway.ensure_connected()
                captured["symbols"] = self.gateway.symbols()
            except Exception as error:  # pragma: no cover - failure path
                captured["error"] = f"{type(error).__name__}: {error}"

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        self.assertNotIn("error", captured, captured.get("error"))
        self.assertIn("EURUSD", captured["symbols"])

    def test_ensure_connected_is_idempotent(self):
        self.gateway.ensure_connected()
        self.gateway.ensure_connected()
        self.gateway.ensure_connected()
        self.assertEqual(self.mt5.initialise_calls, 1)

    def test_ensure_connected_refuses_to_migrate_the_owner(self):
        """Silently rebinding the owner would defeat the guard completely.

        A gateway attached on the wrong thread is an application wiring defect.
        It must be loud, not repaired at runtime.
        """
        self.gateway.connect()
        captured = {}

        def worker():
            try:
                self.gateway.ensure_connected()
            except GatewayError as error:
                captured["error"] = str(error)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertIn("already connected on a different thread", captured.get("error", ""))

    def test_a_failed_attach_does_not_leave_the_gateway_looking_connected(self):
        """`connect` used to assign the module handle before `initialize`
        succeeded, so a refused connection reported itself as attached and was
        never retried."""
        self.mt5.initialise_should_fail = True
        with self.assertRaises(self.module.MT5Unavailable):
            self.gateway.ensure_connected()
        self.assertFalse(self.gateway.is_connected())

        self.mt5.initialise_should_fail = False
        self.assertTrue(self.gateway.ensure_connected())

    def test_reconnect_shuts_down_first(self):
        """`initialize()` on an already-initialised terminal returns True
        without re-attaching, so a reconnect that skipped the shutdown would
        report success and change nothing."""
        self.gateway.ensure_connected()
        self.assertTrue(self.gateway.reconnect())
        self.assertGreaterEqual(self.mt5.shutdown_calls, 1)
        self.assertEqual(self.mt5.initialise_calls, 2)

    def test_reconnect_reports_failure_rather_than_raising(self):
        self.gateway.ensure_connected()
        self.mt5.initialise_should_fail = True
        self.assertFalse(self.gateway.reconnect())


# ===========================================================================
class TestProbe(MT5TestCase):
    def test_a_probe_leaves_no_connection_behind(self):
        """It runs on the UI thread. Anything it left attached would be owned
        by the wrong thread — which is the bug it exists to avoid."""
        probe = self.module.probe_terminal()
        self.assertTrue(probe.available)
        self.assertFalse(self.mt5.initialised)
        self.assertGreaterEqual(self.mt5.shutdown_calls, 1)

    def test_a_probe_reports_the_account_kind(self):
        probe = self.module.probe_terminal()
        self.assertIs(probe.is_demo, True)
        self.assertEqual(probe.login, 5_000_123)

    def test_a_real_account_is_reported_as_such(self):
        self.mt5.account = FakeAccount(trade_mode=1)
        probe = self.module.probe_terminal()
        self.assertIs(probe.is_demo, False)

    def test_no_account_is_unknown_not_not_demo(self):
        """The environment verdict keys off exactly this distinction."""
        self.mt5.account = None
        probe = self.module.probe_terminal()
        self.assertIsNone(probe.is_demo)
        self.assertFalse(probe.account_known)

    def test_an_unreachable_terminal_is_reported_not_raised(self):
        self.mt5.initialise_should_fail = True
        probe = self.module.probe_terminal()
        self.assertFalse(probe.available)
        self.assertIn("not reachable", probe.reason)

    def test_algo_trading_state_is_reported(self):
        self.mt5.terminal.trade_allowed = False
        probe = self.module.probe_terminal()
        self.assertFalse(probe.trade_allowed)


# ===========================================================================
class TestMarketData(MT5TestCase):
    def setUp(self):
        super().setUp()
        self.gateway.ensure_connected()

    def test_symbol_resolution_finds_a_decorated_name(self):
        """Brokers decorate: EURUSD may really be GBPUSD.m. Getting this wrong
        sizes a trade against the wrong contract."""
        self.assertEqual(self.gateway.resolve_symbol("GBPUSD"), "GBPUSD.m")

    def test_an_exact_name_wins(self):
        self.assertEqual(self.gateway.resolve_symbol("EURUSD"), "EURUSD")

    def test_an_unknown_symbol_resolves_to_none_rather_than_a_guess(self):
        self.assertIsNone(self.gateway.resolve_symbol("NOTREAL"))

    def test_the_specification_maps_every_sizing_field(self):
        spec = self.gateway.symbol_spec("XAUUSD")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.digits, 2)
        self.assertEqual(spec.contract_size, 100.0)
        self.assertEqual(spec.volume_step, 0.01)
        self.assertTrue(spec.ready)

    def test_missing_history_returns_an_empty_list_not_a_crash(self):
        """The package returns None on failure. Anything that calls len() on
        that raises TypeError against the real terminal too."""
        self.assertEqual(self.gateway.bars("EURUSD", Timeframe.M5, 100), [])

    def test_history_is_returned_oldest_first(self):
        self.mt5.load_rates("EURUSD", self.mt5.TIMEFRAME_M5, 200)
        bars = self.gateway.bars("EURUSD", Timeframe.M5, 100)
        self.assertEqual(len(bars), 100)
        self.assertLess(bars[0].time, bars[-1].time)

    def test_the_account_maps_the_demo_flag(self):
        account = self.gateway.account()
        self.assertTrue(account.is_demo)

    def test_a_real_account_maps_the_flag_as_false(self):
        self.mt5.account = FakeAccount(trade_mode=1)
        self.assertFalse(self.gateway.account().is_demo)


# ===========================================================================
class TestOrderConstruction(MT5TestCase):
    def setUp(self):
        super().setUp()
        self.gateway.ensure_connected()
        self.request = self._request()

    def _request(self, **overrides) -> OrderRequest:
        """OrderRequest is frozen — deliberately, since it is the exact payload
        that goes to the broker — so a variant is a new instance."""
        fields = dict(
            symbol="EURUSD",
            direction=Direction.LONG,
            volume=0.10,
            price=1.10000,
            stop_loss=1.09800,
            take_profit=1.10400,
            deviation=30,
            magic=20260806,
            comment="alikhande",
        )
        fields.update(overrides)
        return OrderRequest(**fields)

    def _built(self, request: OrderRequest | None = None) -> dict:
        self.gateway.check_order(request or self.request)
        return self.mt5.checked[-1]

    def test_a_long_becomes_a_buy(self):
        self.assertEqual(self._built()["type"], self.mt5.ORDER_TYPE_BUY)

    def test_a_short_becomes_a_sell(self):
        built = self._built(self._request(direction=Direction.SHORT))
        self.assertEqual(built["type"], self.mt5.ORDER_TYPE_SELL)

    def test_the_stops_are_carried_through(self):
        built = self._built()
        self.assertAlmostEqual(built["sl"], 1.09800)
        self.assertAlmostEqual(built["tp"], 1.10400)

    def test_fok_is_used_when_the_symbol_supports_it(self):
        self.mt5.symbols_map["EURUSD"].filling_mode = ORDER_FILLING_IOC | 1
        self.assertEqual(self._built()["type_filling"], self.mt5.ORDER_FILLING_FOK)

    def test_ioc_is_used_when_only_ioc_is_supported(self):
        self.mt5.symbols_map["EURUSD"].filling_mode = 2
        self.assertEqual(self._built()["type_filling"], self.mt5.ORDER_FILLING_IOC)

    def test_a_symbol_supporting_neither_falls_back_to_return(self):
        """A real broker configuration, and the one that used to produce a
        guaranteed 10030: the code defaulted to IOC for a symbol that had just
        said it does not support IOC."""
        self.mt5.symbols_map["EURUSD"].filling_mode = 0
        self.assertEqual(self._built()["type_filling"], self.mt5.ORDER_FILLING_RETURN)

    def test_the_comment_is_truncated_to_what_metatrader_accepts(self):
        """MetaTrader truncates to a 32-byte field itself. Doing it here means
        the comment this application recorded matches the one the broker holds,
        so reconciliation is not comparing a string to its own truncated copy."""
        built = self._built(self._request(comment="x" * 200))
        self.assertLessEqual(len(built["comment"]), 31)


# ===========================================================================
class TestSendRefusals(MT5TestCase):
    """The adapter's own real-account refusal, which shares no code with the
    execution engine's."""

    def setUp(self):
        super().setUp()
        self.gateway.ensure_connected()
        self.request = OrderRequest(
            symbol="EURUSD",
            direction=Direction.LONG,
            volume=0.10,
            price=1.10000,
            stop_loss=1.09800,
            take_profit=1.10400,
            deviation=30,
            magic=1,
            comment="alikhande",
        )

    def test_a_demo_account_sends(self):
        """The control. Without it every refusal test below would pass on a
        build where sending was simply broken."""
        result = self.gateway.send_order(self.request)
        self.assertTrue(result.ok)
        self.assertEqual(len(self.mt5.sent), 1)

    def test_a_real_account_is_refused_by_the_adapter_itself(self):
        self.mt5.account = FakeAccount(trade_mode=1)
        result = self.gateway.send_order(self.request)
        self.assertFalse(result.ok)
        self.assertEqual(result.comment, "REAL_ACCOUNT_BLOCKED")
        self.assertEqual(self.mt5.sent, [], "an order reached a live account")

    def test_a_contest_account_is_refused_too(self):
        """trade_mode 2. Not demo, so not tradeable by this build."""
        self.mt5.account = FakeAccount(trade_mode=2)
        result = self.gateway.send_order(self.request)
        self.assertFalse(result.ok)
        self.assertEqual(self.mt5.sent, [])

    def test_an_unreadable_account_is_refused(self):
        self.mt5.account = None
        result = self.gateway.send_order(self.request)
        self.assertFalse(result.ok)
        self.assertEqual(result.comment, "NO_ACCOUNT")
        self.assertEqual(self.mt5.sent, [])

    def test_a_rejection_is_reported_as_not_ok(self):
        self.mt5.send_retcode = 10016  # INVALID_STOPS
        result = self.gateway.send_order(self.request)
        self.assertFalse(result.ok)
        self.assertEqual(result.retcode, 10016)

    def test_a_partial_fill_counts_as_accepted(self):
        self.mt5.send_retcode = 10010  # DONE_PARTIAL
        self.assertTrue(self.gateway.send_order(self.request).ok)


if __name__ == "__main__":
    unittest.main()
