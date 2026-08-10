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
        from alikhande.ui.components import StatusChip

        colours = [colour for colour, _ in StatusChip.TONES.values()]
        self.assertEqual(len(colours), len(set(colours)))

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


if __name__ == "__main__":
    unittest.main()
