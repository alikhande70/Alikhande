"""One thread owns the broker. This proves it, rather than documenting it.

The MetaTrader5 package keeps process-global connection state and refuses calls
from any thread but the one that attached. That single fact has now produced
**two** separate defects in this codebase, both silent, both invisible to a
green suite:

1. The gateway attached on the UI thread while the scan worker made the calls,
   so every live pass raised and the window reported "disconnected" against a
   healthy terminal.
2. With that fixed, the UI thread still reached the gateway from `_on_snapshot`
   — asking the engine for positions and working orders — which raised, was
   swallowed by the engine's `_safe_*` wrappers, and rendered as an account
   with no open positions and zero exposure.

Both were found by attaching a gateway that behaves like MetaTrader's and
watching who calls it. That is what this file automates.

The offline gateway has no such guard, which is exactly why neither defect
showed up in any other test: offline, calling from the wrong thread works
perfectly.
"""

from __future__ import annotations

import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from alikhande.adapters.offline.gateway import OfflineGateway
from alikhande.core.ports import GatewayError

try:
    from PySide6.QtWidgets import QApplication

    HAS_QT = True
except ImportError:  # pragma: no cover
    HAS_QT = False


class ThreadBoundGateway(OfflineGateway):
    """An offline gateway with MetaTrader's owner-thread rule bolted on.

    Every method a live adapter guards is guarded here, and a violation is
    recorded as well as raised — recorded because the engine swallows gateway
    exceptions by design, so a test that only watched for the exception would
    see nothing at all.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._owner: int | None = None
        self.violations: list[str] = []

    def ensure_connected(self) -> bool:
        self._owner = threading.get_ident()
        return True

    def reconnect(self) -> bool:
        return self.ensure_connected()

    def _guard(self, name: str) -> None:
        if self._owner is not None and threading.get_ident() != self._owner:
            self.violations.append(name)
            raise GatewayError(f"{name} called from a thread other than the owner")

    # Every gateway method the application actually calls.
    def server_time(self):
        self._guard("server_time")
        return super().server_time()

    def symbols(self):
        self._guard("symbols")
        return super().symbols()

    def resolve_symbol(self, requested):
        self._guard("resolve_symbol")
        return super().resolve_symbol(requested)

    def symbol_spec(self, symbol):
        self._guard("symbol_spec")
        return super().symbol_spec(symbol)

    def tick(self, symbol):
        self._guard("tick")
        return super().tick(symbol)

    def bars(self, symbol, timeframe, count):
        self._guard("bars")
        return super().bars(symbol, timeframe, count)

    def account(self):
        self._guard("account")
        return super().account()

    def positions(self, magic=None):
        self._guard("positions")
        return super().positions(magic)

    def orders(self, magic=None):
        self._guard("orders")
        return super().orders(magic)

    def history_orders(self, since, until, magic=None):
        self._guard("history_orders")
        return super().history_orders(since, until, magic)

    def history_deals(self, since, until, magic=None):
        self._guard("history_deals")
        return super().history_deals(since, until, magic)

    def calc_profit(self, *args, **kwargs):
        self._guard("calc_profit")
        return super().calc_profit(*args, **kwargs)

    def calc_margin(self, *args, **kwargs):
        self._guard("calc_margin")
        return super().calc_margin(*args, **kwargs)


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class TestOnlyTheWorkerTouchesTheBroker(unittest.TestCase):
    def setUp(self):
        from alikhande.app.backtest import BACKTEST_TIMEFRAMES
        from alikhande.config import AppConfig

        self.config = AppConfig()
        self.gateway = ThreadBoundGateway()
        self.gateway.load_synthetic(self.config.symbols, BACKTEST_TIMEFRAMES, 400)
        self.gateway.set_cursor(
            self.gateway.series_length(self.config.symbols[0], BACKTEST_TIMEFRAMES[0])
        )

        from alikhande.app.engine import ScanEngine
        from alikhande.core.runtime import detect_runtime, environment_plan
        from alikhande.ui import main_window as mw

        self.application = QApplication.instance() or QApplication([])
        self.window = mw.MainWindow(
            ScanEngine(self.gateway, self.config),
            self.config,
            detect_runtime(connected=False, replay=False),
            environment_plan("BACKTEST", mw.data_directory(), connected=False),
            None,
        )

    def tearDown(self):
        self.window._worker.stop()
        self.window._thread.quit()
        self.window._thread.wait(3000)

    def _settle(self, passes: int = 4, timeout: float = 20.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.application.processEvents()
            if getattr(self.window, "_passes_seen", 0) >= passes:
                return
            time.sleep(0.05)
        self.fail("the scan worker never produced enough passes")

    def test_scanning_never_touches_the_gateway_from_the_ui_thread(self):
        """The regression that rendered a live account as having no positions."""
        self._settle()
        self.assertEqual(
            sorted(set(self.gateway.violations)),
            [],
            "the UI thread reached the broker; on MetaTrader these calls raise, "
            "are swallowed, and render as an account with nothing open",
        )

    def test_the_snapshot_carries_the_broker_state_the_views_need(self):
        """The other half of the same fix: if the views cannot get positions off
        the snapshot they will reach for the engine again."""
        self._settle()
        snapshot = self.window._last_snapshot
        self.assertIsNotNone(snapshot)
        for field in ("positions", "orders", "exposure", "account"):
            self.assertTrue(
                hasattr(snapshot, field), f"the snapshot has no `{field}`"
            )
        self.assertIsNotNone(snapshot.exposure, "exposure must be computed by the worker")

    def test_the_ui_thread_actions_outside_a_pass_stay_off_the_gateway(self):
        """Diagnostics, the recovery report and a notification all run outside a
        scan pass and all used to reach the broker for a clock or an account."""
        self._settle()
        self.gateway.violations.clear()

        self.window._write_diagnostics()
        self.window._report_recovery()
        self.window._notify("backup.written", "test", self.window._now())
        self.window._run_backup(quiet=True)

        self.assertEqual(sorted(set(self.gateway.violations)), [])

    def test_the_engine_offers_no_way_for_a_view_to_reach_the_broker(self):
        """Structural, not behavioural. These accessors each called the gateway
        and every caller was on the UI thread; leaving them available means the
        next view that needs positions reintroduces the defect."""
        from alikhande.app.engine import ScanEngine

        for removed in ("own_positions", "working_orders", "exposure_summary",
                        "account_snapshot"):
            self.assertFalse(
                hasattr(ScanEngine, removed),
                f"ScanEngine.{removed} is back, and it reaches the gateway",
            )


if __name__ == "__main__":
    unittest.main()
