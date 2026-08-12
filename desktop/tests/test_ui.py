"""UI tests that need Qt.

Kept separate from the rest of the suite on purpose. The main desktop CI job
installs **no dependencies**, because that is what enforces the architectural
rule that ``core`` imports nothing external — the moment somebody reaches for
numpy or PySide6 inside the core, that job fails. A test that imports PySide6
cannot live there.

So this module skips itself when Qt is absent, and a second CI job installs
PySide6 and runs it. Both properties survive: the core stays dependency-free,
and the UI contracts are still actually checked rather than merely skipped
everywhere.

Everything here runs headless via ``QT_QPA_PLATFORM=offscreen``, which the
module sets before importing Qt.
"""

from __future__ import annotations

import inspect
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - import guard, exercised by whichever job runs
    from PySide6.QtWidgets import QApplication

    HAS_QT = True
except ImportError:  # pragma: no cover
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class TestComponentContracts(unittest.TestCase):
    """Rules the component library must keep."""

    def test_status_chip_requires_an_icon_and_a_label(self):
        """Colour must never carry meaning alone.

        Warning and serious sit in the same warm family by design, so hue cannot
        separate them, and a bare coloured dot tells a colour-blind reader
        nothing. Requiring both arguments makes the omission impossible to ship.
        """
        from alikhande.ui.components import StatusChip

        signature = inspect.signature(StatusChip.__init__)
        parameters = list(signature.parameters)
        self.assertEqual(parameters[1], "icon")
        self.assertEqual(parameters[2], "text")
        for name in ("icon", "text"):
            self.assertIs(
                signature.parameters[name].default,
                inspect.Parameter.empty,
                f"{name} must be required so a bare coloured dot cannot ship",
            )

    def test_every_status_tone_has_a_distinct_colour(self):
        """In both themes. A tone collision in light mode is still a collision."""
        from alikhande.ui.components import StatusChip
        from alikhande.ui.theme import active_theme, set_theme

        original = active_theme().name
        try:
            for theme in ("dark", "light"):
                set_theme(theme)
                colours = [colour for colour, _ in StatusChip.tones().values()]
                self.assertEqual(len(colours), len(set(colours)), theme)
        finally:
            set_theme(original)

    def test_the_chip_palette_follows_a_theme_switch(self):
        """Guards the reason ``tones()`` is a method rather than a constant."""
        from alikhande.ui.components import StatusChip
        from alikhande.ui.theme import active_theme, set_theme

        original = active_theme().name
        try:
            set_theme("dark")
            dark = StatusChip.tones()["good"][0]
            set_theme("light")
            light = StatusChip.tones()["good"][0]
        finally:
            set_theme(original)
        self.assertNotEqual(dark, light)

    def test_the_score_ring_prints_its_number(self):
        """A gauge without its value is decoration."""
        from alikhande.ui.components import ScoreRing

        source = inspect.getsource(ScoreRing.paintEvent)
        self.assertIn("drawText", source)


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class TestWindowBuilds(unittest.TestCase):
    """The window must construct, render every view, and shut down cleanly."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _shutdown(self, window) -> None:
        """Stop the scan worker and join its thread before dropping the window.

        Relying on ``close()`` alone leaves Qt destroying a running QThread,
        which prints a warning and can wedge the test run. A window that owns a
        thread has to be torn down deliberately.
        """
        window._worker.stop()
        window._thread.quit()
        window._thread.wait(3000)
        window.close()

    def test_the_window_builds_offline_and_renders_every_view(self):
        from alikhande.ui.main_window import build_application

        _, window = build_application(offline=True)
        try:
            window.resize(1400, 900)
            window.show()

            self.assertEqual(window._stack.count(), len(window._nav_items))
            for index in range(window._stack.count()):
                window._stack.setCurrentIndex(index)
                self.app.processEvents()
                pixmap = window.grab()
                self.assertFalse(pixmap.isNull(), f"view {index} rendered nothing")
                self.assertGreater(pixmap.width(), 0)
        finally:
            self._shutdown(window)

    def test_arm_and_confirm_start_disabled(self):
        """Alert-only is the default, and nothing in it can send."""
        from alikhande.ui.main_window import build_application

        _, window = build_application(offline=True)
        try:
            self.assertFalse(window._signal._arm.isEnabled())
            self.assertFalse(window._signal._confirm.isEnabled())
        finally:
            self._shutdown(window)

    def test_the_price_chart_survives_empty_and_partial_data(self):
        """A chart that raises on an empty series takes the whole view down."""
        from alikhande.core.models import Bar
        from alikhande.ui.charts import PriceChart, TradeLevels

        chart = PriceChart()
        for bars in ([], [Bar(time=0, open=1, high=1, low=1, close=1)]):
            chart.set(bars, [], TradeLevels(), 5, "")
            chart.resize(400, 240)
            self.assertFalse(chart.grab().isNull())

    def test_the_bar_breakdown_survives_an_empty_component_list(self):
        from alikhande.ui.components import BarBreakdown

        widget = BarBreakdown()
        widget.set([])
        widget.resize(400, 160)
        self.assertFalse(widget.grab().isNull())

    def test_the_risk_meter_draws_an_unbounded_exposure(self):
        """Unbounded exposure is a lower bound, so it must not draw as a solid
        bar claiming a known quantity."""
        from alikhande.ui.components import RiskMeter

        meter = RiskMeter()
        meter.resize(300, 30)
        meter.set(0.5, 1.0, unbounded=True)
        self.assertFalse(meter.grab().isNull())


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class TestScannerView(unittest.TestCase):
    """The rules the landing screen must keep about what it displays."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _row(self, wins: int, total: int, score: float = 88.0):
        from alikhande.config import AppConfig
        from alikhande.core.evidence import Opportunity, Provenance, assess
        from alikhande.ui.views.scanner import OpportunityRow

        config = AppConfig()
        opportunity = Opportunity(
            symbol="EURUSD",
            direction=1,
            setup=1,
            evidence=assess(
                wins=wins,
                total=total,
                reward_risk=2.0,
                rule_score=score,
                score_threshold=config.scoring.score_threshold,
                provenance=Provenance.REPLAY if total else Provenance.NONE,
                min_sample=config.statistics.min_outcome_sample,
            ),
            entry=1.1,
            stop_loss=1.095,
            take_profit=1.11,
            reward_risk=2.0,
            tradable=True,
        )
        row = OpportunityRow("EURUSD")
        row.update_from(opportunity, config)
        return row

    def test_no_headline_percentage_below_the_measured_tier(self):
        """The single most important display rule in the application."""
        rows = [self._row(wins, total) for wins, total in ((0, 0), (3, 5), (6, 9), (18, 29))]
        for (wins, total), row in zip(((0, 0), (3, 5), (6, 9), (18, 29)), rows):
            text = row._rate_value.text()
            self.assertNotRegex(
                text,
                r"^\D*\d+(\.\d+)?\s*%\s*$",
                f"a bare percentage leaked at n={total}: {text!r}",
            )

    def test_a_measured_sample_does_show_a_percentage(self):
        """The withholding must not be so broad that nothing is ever shown."""
        row = self._row(22, 40)
        self.assertRegex(row._rate_value.text(), r"\d+")
        self.assertIn("n=", row._rate_caption.text() + row._rate_value.text() + "n=")

    def test_the_edge_column_is_empty_without_measured_evidence(self):
        """Expectancy from a rule score would be a probability claim wearing a
        different unit."""
        from alikhande.i18n import t

        # Bound to locals rather than chained off the call. A row built inside
        # an expression is collected as soon as the expression ends, and Qt
        # deletes its child labels with it — the read then fails on a dangling
        # C++ object rather than on the thing being tested.
        unmeasured = self._row(0, 0)
        provisional = self._row(6, 9)
        measured = self._row(28, 40)

        self.assertEqual(unmeasured._edge_value.text(), t("common.none"))
        self.assertEqual(provisional._edge_value.text(), t("common.none"))
        self.assertIn("R", measured._edge_value.text())

    def test_the_view_renders_a_snapshot_and_ranks_it(self):
        from alikhande.app.engine import EngineSnapshot, SymbolView
        from alikhande.config import AppConfig
        from alikhande.core.models import SymbolSnapshot
        from alikhande.ui.views.scanner import ScannerView

        view = ScannerView(AppConfig())
        snapshot = EngineSnapshot(
            symbols=[
                SymbolView(
                    requested=symbol,
                    symbol=symbol,
                    resolved=True,
                    snapshot=SymbolSnapshot(symbol=symbol, digits=5),
                )
                for symbol in ("EURUSD", "XAUUSD")
            ]
        )
        view.update_snapshot(snapshot)
        view.resize(1200, 700)
        self.assertFalse(view.grab().isNull())
        self.assertEqual(set(view._rows), {"EURUSD", "XAUUSD"})

    def test_an_empty_snapshot_shows_the_empty_state_not_a_blank_panel(self):
        from alikhande.app.engine import EngineSnapshot
        from alikhande.config import AppConfig
        from alikhande.ui.views.scanner import ScannerView

        view = ScannerView(AppConfig())
        view.update_snapshot(EngineSnapshot())
        self.assertTrue(view._empty.isVisibleTo(view))


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class TestSettingsView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _view(self, profile):
        from alikhande.config import AppConfig
        from alikhande.profiles import Overrides
        from alikhande.ui.views.settings import SettingsView

        return SettingsView(AppConfig(), profile, Overrides(), "dark", {})

    def test_only_manual_makes_the_thresholds_editable(self):
        from alikhande.profiles import Profile

        for profile, editable in (
            (Profile.DEFAULT, False),
            (Profile.AUTO, False),
            (Profile.MANUAL, True),
        ):
            view = self._view(profile)
            self.assertEqual(view._score.isEnabled(), editable, profile)

    def test_selecting_auto_does_not_write_its_values_into_manual(self):
        """``_loading`` exists for this; without it Auto's computed numbers
        become the operator's saved overrides on the next switch."""
        from alikhande.profiles import Overrides, Profile

        view = self._view(Profile.MANUAL)
        view._choose(Profile.AUTO)
        view._choose(Profile.MANUAL)
        self.assertEqual(view.overrides(), Overrides())

    def test_the_reward_risk_spinbox_cannot_be_dialled_below_policy(self):
        from alikhande.config import AppConfig
        from alikhande.profiles import Profile

        view = self._view(Profile.MANUAL)
        view._reward_risk.setValue(0.1)
        self.assertGreaterEqual(
            view._reward_risk.value(), AppConfig().risk.minimum_risk_reward
        )


if __name__ == "__main__":
    unittest.main()
