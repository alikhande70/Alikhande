"""``doctor``, and the packaging invariants it cannot check.

``doctor`` is the first thing that runs on the Windows machine before a demo
account is ever attached, so it is the one command whose output has to be
trusted without a second opinion. These tests drive its Windows branch against
the fake terminal — the branch that, on the machine this was built on, can
never execute.

The packaging tests are here rather than in a build script because the failure
they prevent is invisible until the worst possible moment: an executable that
runs perfectly offline and dies the instant it touches a broker.
"""

from __future__ import annotations

import argparse
import io
import contextlib
import os
import platform
import tempfile
import unittest
from pathlib import Path

try:  # pragma: no cover - depends on how the suite was launched
    from .fake_mt5 import FakeAccount, FakeMT5, install, uninstall
except ImportError:  # pragma: no cover
    from fake_mt5 import FakeAccount, FakeMT5, install, uninstall

try:
    import PySide6  # noqa: F401

    HAS_QT = True
except ImportError:  # pragma: no cover - the dependency-free job
    HAS_QT = False


@contextlib.contextmanager
def _pyside6_unavailable():
    """Make ``import PySide6`` fail for the duration.

    So the "no UI toolkit" tests assert the same thing in both CI jobs instead
    of depending on what the runner happens to have installed.
    """
    import sys

    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if name == "PySide6" or name.startswith("PySide6."):
                raise ImportError(f"No module named {name!r}")
            return None

    blocker = Blocker()
    cached = {k: v for k, v in sys.modules.items() if k.startswith("PySide6")}
    for name in cached:
        del sys.modules[name]
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(cached)


class DoctorTestCase(unittest.TestCase):
    """Drives the Windows branch on whatever machine the suite runs on."""

    def setUp(self):
        self._data = tempfile.TemporaryDirectory()
        self._xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self._data.name
        calendar = Path(self._data.name) / "AlikhandeScanner" / "calendar.csv"
        calendar.parent.mkdir(parents=True, exist_ok=True)
        calendar.write_text(
            "time,currency,name,importance,coverage_until\n"
            "1700000000,USD,Fixture,LOW,4102444800\n",
            encoding="utf-8",
        )
        self.mt5 = install(FakeMT5())
        for symbol in list(self.mt5.symbols_map):
            self.mt5.load_rates(symbol, self.mt5.TIMEFRAME_M5, 400)
        self._system = platform.system
        self._release = platform.release
        platform.system = lambda: "Windows"
        platform.release = lambda: "11"

    def tearDown(self):
        platform.system = self._system
        platform.release = self._release
        uninstall()
        if self._xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self._xdg
        self._data.cleanup()

    def run_doctor(self) -> tuple[int, str]:
        from alikhande.__main__ import _cmd_doctor

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = _cmd_doctor(argparse.Namespace())
        return code, buffer.getvalue()


# ===========================================================================
class TestDoctorReportsTheFix(DoctorTestCase):
    """Every failure has to name the action, not just the symptom.

    "cannot connect" has at least four unrelated causes and they need four
    different responses, which is why this command exists at all.
    """

    def test_an_unreachable_terminal_says_to_start_it(self):
        self.mt5.initialise_should_fail = True
        code, output = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("NOT REACHABLE", output)
        self.assertIn("Start MetaTrader 5", output)

    def test_algo_trading_off_names_the_menu_path(self):
        self.mt5.terminal.trade_allowed = False
        code, output = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("DISABLED", output)
        self.assertIn("Expert Advisors", output)

    def test_a_missing_symbol_says_to_add_it_to_market_watch(self):
        code, output = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("NOT FOUND", output)
        self.assertIn("Market Watch", output)

    def test_thin_history_says_to_scroll_the_chart_back(self):
        for symbol in self.mt5.symbols_map:
            self.mt5.load_rates(symbol, self.mt5.TIMEFRAME_M5, 20)
        _code, output = self.run_doctor()
        self.assertIn("INSUFFICIENT", output)
        self.assertIn("scroll back", output)

    def test_an_unreadable_account_is_reported_as_such(self):
        self.mt5.account = None
        code, output = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("NOT READABLE", output)

    def test_a_real_account_is_reported_and_explained(self):
        self.mt5.account = FakeAccount(trade_mode=1)
        code, output = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("[REAL]", output)
        self.assertIn("never sends an order on a non-demo account", output)

    def test_the_symbol_mapping_is_shown_not_just_counted(self):
        """A broker that serves GBPUSD as GBPUSD.m is the normal case, and an
        operator has to be able to see which contract was chosen."""
        _code, output = self.run_doctor()
        self.assertIn("GBPUSD -> GBPUSD.m", output)

    def _make_every_symbol_available(self) -> None:
        from alikhande.config import AppConfig

        self.mt5.symbols_map = {}
        for requested in AppConfig().symbols:
            self.mt5.symbols_map[requested] = _symbol_for(requested)
            self.mt5.load_rates(requested, self.mt5.TIMEFRAME_M5, 400)

    @unittest.skipUnless(HAS_QT, "a machine with no UI toolkit is not a ready machine")
    def test_a_machine_with_all_inspected_prerequisites_exits_zero(self):
        """The gate passes only when *every* prerequisite is met, and the UI
        toolkit is one of them.

        Skipped rather than adjusted when Qt is absent: "the machine gate
        passes" is a claim about the machine, and a machine that cannot open a
        window cannot run a demo session. `doctor` is right to block it — this
        test simply cannot arrange the precondition in the dependency-free job.
        The property that *is* checkable there is asserted below instead.
        """
        self._make_every_symbol_available()

        code, output = self.run_doctor()
        self.assertIn("MACHINE GATE PASS", output)
        self.assertNotIn("MACHINE GATE BLOCKED", output)
        self.assertEqual(code, 0)

    def test_a_machine_without_the_ui_toolkit_is_blocked(self):
        """What the Qt-skipped test above cannot check, checked here.

        The import is blocked for the duration rather than left to whatever the
        runner has installed, so this asserts the same thing in both CI jobs.
        """
        self._make_every_symbol_available()
        with _pyside6_unavailable():
            code, output = self.run_doctor()
        self.assertIn("PySide6           MISSING", output)
        self.assertIn("MACHINE GATE BLOCKED", output)
        self.assertEqual(code, 1, "a machine that cannot open a window is not ready")

    def test_a_missing_ui_toolkit_does_not_stop_the_terminal_checks(self):
        """Absent Qt is a reason to block, not a reason to stop looking. An
        operator setting a machine up wants every problem in one pass."""
        self._make_every_symbol_available()
        with _pyside6_unavailable():
            _code, output = self.run_doctor()
        for expected in ("terminal", "algo trading", "calendar", "symbols"):
            self.assertIn(expected, output)

    def test_a_missing_calendar_blocks_live_demo_readiness(self):
        from alikhande.app.paths import data_directory
        from alikhande.config import AppConfig

        (data_directory() / "calendar.csv").unlink()
        self.mt5.symbols_map = {}
        for requested in AppConfig().symbols:
            self.mt5.symbols_map[requested] = _symbol_for(requested)
            self.mt5.load_rates(requested, self.mt5.TIMEFRAME_M5, 400)
        code, output = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("calendar", output)
        self.assertIn("MISSING", output)

    def test_doctor_leaves_no_connection_behind(self):
        """It runs on the main thread. A connection left attached here would be
        owned by the wrong thread for anything that ran afterwards."""
        self.run_doctor()
        self.assertFalse(self.mt5.initialised)


def _symbol_for(name: str):
    try:
        from .fake_mt5 import FakeSymbol
    except ImportError:  # pragma: no cover
        from fake_mt5 import FakeSymbol
    if name.startswith("XAU"):
        return FakeSymbol(
            name=name, digits=2, point=0.01, trade_tick_size=0.01,
            trade_contract_size=100.0, currency_base="XAU", currency_margin="XAU",
        )
    return FakeSymbol(name=name, currency_base=name[:3], currency_profit=name[3:])


# ===========================================================================
class TestPackagingInvariants(unittest.TestCase):
    """Things a green test suite cannot tell you about the executable."""

    def setUp(self):
        self.spec = (Path(__file__).resolve().parent.parent / "packaging" / "alikhande.spec")
        self.assertTrue(self.spec.exists(), "the PyInstaller spec is missing")
        self.text = self.spec.read_text(encoding="utf-8")

    def test_numpy_is_not_excluded(self):
        """The MetaTrader5 wheel depends on numpy and `copy_rates_from_pos`
        returns a numpy structured array which the gateway reads by field name.

        Excluding it looks like free weight — the pure core never touches numpy
        — and produces an executable that runs perfectly offline and fails the
        instant it touches a terminal.
        """
        excludes = self.text.split("excludes=[", 1)[1].split("]", 1)[0]
        stripped = "\n".join(
            line for line in excludes.splitlines() if not line.strip().startswith("#")
        )
        self.assertNotIn('"numpy"', stripped)

    def test_metatrader5_is_a_hidden_import(self):
        """It is imported inside a try/except, so the dependency graph does not
        see it and PyInstaller would leave it out."""
        self.assertIn('"MetaTrader5"', self.text)

    def test_the_build_script_refuses_to_package_a_red_build(self):
        """An executable is the artefact people actually run. Shipping one from
        a red suite is how an untested build reaches a live terminal."""
        script = self.spec.parent / "build_windows.ps1"
        self.assertTrue(script.exists())
        body = script.read_text(encoding="utf-8")
        self.assertIn("unittest discover", body, "the build script runs no tests")
        self.assertIn(
            "refusing to package",
            body,
            "the build script runs the tests but does not stop on failure",
        )


if __name__ == "__main__":
    unittest.main()
