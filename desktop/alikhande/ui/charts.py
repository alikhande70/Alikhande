"""Chart widgets, painted directly.

The v1 panel had no picture of price at all, which for a scanner whose entire
thesis is *structure* was the single largest omission: it asserted "price is
inside a demand zone" and gave the operator no way to see it and disagree.

Two charts:

``PriceChart``
    Candles, the structural zones as bands, and the entry / stop / target levels
    as direct-labelled lines. This is the one place the operator can check the
    system's claim against the market.

``Sparkline``
    A compact trend line for a watchlist row. No axes, no grid — it answers
    "which way has this been going" and nothing else.

Both follow the same rules as any other chart here: recessive grid, thin marks,
direct labels rather than a legend where there is room, and one shared price
scale (never two).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..core.enums import Direction, ZoneType
from ..core.models import Bar, Zone
from ..i18n import fmt_count, t
from .theme import PALETTE, TYPE


@dataclass
class TradeLevels:
    """The three levels a plan defines. Zero means "not set" and is not drawn."""

    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    direction: int = 0


class PriceChart(QWidget):
    """Candles with structural zones and the plan's levels drawn on them."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: list[Bar] = []
        self._zones: list[Zone] = []
        self._levels = TradeLevels()
        self._digits = 5
        self._title = ""
        self.setMinimumHeight(260)

    def set(
        self,
        bars: list[Bar],
        zones: list[Zone],
        levels: TradeLevels,
        digits: int = 5,
        title: str = "",
    ) -> None:
        self._bars = bars[-120:] if bars else []
        self._zones = zones or []
        self._levels = levels
        self._digits = digits
        self._title = title
        self.update()

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPixelSize(TYPE.micro)
        painter.setFont(font)

        if len(self._bars) < 3:
            painter.setPen(QColor(PALETTE.ink_faint))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Waiting for price history",
            )
            painter.end()
            return

        metrics = QFontMetrics(painter.font())
        # Size the gutter from a REAL formatted price, not a guess at its width.
        # "0" * (digits + 3) is five characters for gold, where the actual label
        # is "2023.22" — and the difference clipped the leading digit off every
        # axis label, which is the one part of a price you cannot infer.
        sample = max(b.high for b in self._bars)
        widest = max(
            metrics.horizontalAdvance(f"{sample:.{self._digits}f}"),
            metrics.horizontalAdvance(f"TARGET {sample:.{self._digits}f}"),
        )
        right_gutter = widest + 16
        top, bottom, left = 8, 20, 4
        plot = QRectF(
            left,
            top,
            max(40.0, self.width() - left - right_gutter),
            max(40.0, self.height() - top - bottom),
        )

        # ---- price scale ---------------------------------------------------
        # One scale for everything on the chart. The zones and levels must sit
        # in the same space as the candles or the picture is a lie.
        # Price sets the scale. Levels and zones may stretch it, but only within
        # a bounded margin: letting a zone 40 ATR away expand the range squashes
        # every candle into a line, and a chart whose candles are unreadable has
        # stopped being evidence about price.
        highs = [b.high for b in self._bars]
        lows = [b.low for b in self._bars]
        price_low, price_high = min(lows), max(highs)
        price_span = price_high - price_low
        if price_span <= 0:
            painter.end()
            return

        limit = price_span * 0.55
        low, high = price_low, price_high
        for value in (self._levels.entry, self._levels.stop, self._levels.target):
            if value > 0:
                low = min(low, max(value, price_low - limit))
                high = max(high, min(value, price_high + limit))
        for zone in self._visible_zones(price_low, price_high):
            low = min(low, max(zone.low, price_low - limit))
            high = max(high, min(zone.high, price_high + limit))

        span = high - low
        pad = span * 0.06
        low -= pad
        high += pad
        span = high - low

        def y_of(price: float) -> float:
            return plot.bottom() - (price - low) / span * plot.height()

        # ---- grid ----------------------------------------------------------
        painter.setPen(QPen(QColor(PALETTE.grid), 1))
        for step in range(0, 5):
            y = plot.top() + plot.height() * step / 4.0
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))

        # Gridlines without values are decoration. The labels go in the gutter,
        # recessive, so they inform without competing with the candles.
        painter.setPen(QColor(PALETTE.ink_faint))
        for step in range(0, 5):
            y = plot.top() + plot.height() * step / 4.0
            value = high - span * step / 4.0
            painter.drawText(
                QRectF(plot.right() + 5, y - 7, right_gutter - 7, 14),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                f"{value:.{self._digits}f}",
            )

        # ---- zones ---------------------------------------------------------
        # Drawn under the candles so price stays the figure and structure the
        # ground. A band the same weight as the candles competes with them.
        for zone in self._visible_zones(min(lows), max(highs)):
            colour = QColor(PALETTE.short if zone.type == ZoneType.SUPPLY else PALETTE.long)
            colour.setAlpha(30)
            band = QRectF(
                plot.left(),
                y_of(zone.high),
                plot.width(),
                max(2.0, y_of(zone.low) - y_of(zone.high)),
            )
            painter.fillRect(band, colour)

            edge = QColor(PALETTE.short if zone.type == ZoneType.SUPPLY else PALETTE.long)
            edge.setAlpha(90)
            painter.setPen(QPen(edge, 1, Qt.PenStyle.DotLine))
            painter.drawLine(
                int(band.left()), int(band.top()), int(band.right()), int(band.top())
            )
            painter.drawLine(
                int(band.left()), int(band.bottom()), int(band.right()), int(band.bottom())
            )

        # ---- candles -------------------------------------------------------
        count = len(self._bars)
        slot = plot.width() / count
        body_width = max(2.2, min(11.0, slot * 0.68))

        for index, bar in enumerate(self._bars):
            x = plot.left() + slot * (index + 0.5)
            rising = bar.close >= bar.open
            # Candles are neutral. An up bar and a down bar are not a signal —
            # they are the terrain the signal sits on — and tinting several
            # hundred of them drowns out the four things on this chart that do
            # carry meaning: the zone, the entry, the stop and the target.
            colour = QColor(PALETTE.candle_up if rising else PALETTE.candle_down)

            painter.setPen(QPen(colour, 1))
            painter.drawLine(
                QPointF(x, y_of(bar.high)), QPointF(x, y_of(bar.low))
            )

            open_y, close_y = y_of(bar.open), y_of(bar.close)
            body = QRectF(
                x - body_width / 2.0,
                min(open_y, close_y),
                body_width,
                max(1.2, abs(close_y - open_y)),
            )
            painter.fillRect(body, colour)

        # ---- plan levels ---------------------------------------------------
        levels = [
            (self._levels.entry, PALETTE.ink, "ENTRY", Qt.PenStyle.SolidLine),
            (self._levels.stop, PALETTE.critical, "STOP", Qt.PenStyle.DashLine),
            (self._levels.target, PALETTE.good, "TARGET", Qt.PenStyle.DashLine),
        ]
        for price, colour, name, style in levels:
            if price <= 0:
                continue
            y = y_of(price)
            painter.setPen(QPen(QColor(colour), 1, style))
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))

            # Direct label in the gutter. A legend would make the reader look
            # away from the line to find out what it is.
            text = f"{name} {price:.{self._digits}f}"
            box = QRectF(plot.right() + 5, y - 8, right_gutter - 7, 16)
            painter.fillRect(box, QColor(PALETTE.surface_high))
            painter.setPen(QColor(colour))
            painter.drawText(
                box,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                text,
            )

        # ---- axis ----------------------------------------------------------
        painter.setPen(QColor(PALETTE.ink_faint))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 3, plot.width(), 14),
            int(Qt.AlignmentFlag.AlignLeft),
            self._title or t("chart.bars", count=fmt_count(count)),
        )
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 3, plot.width(), 14),
            int(Qt.AlignmentFlag.AlignRight),
            t("chart.zones"),
        )
        painter.end()

    def _visible_zones(self, low: float, high: float) -> list[Zone]:
        """Zones near the visible price range.

        A zone hundreds of pips away is real but would flatten the price scale
        until the candles are a line. Restricting to what price can plausibly
        reach keeps the chart legible without hiding anything relevant.
        """
        span = high - low
        if span <= 0:
            return []
        # Only zones price could plausibly reach from here. A level far outside
        # the visible range is real but irrelevant to this decision, and drawing
        # it costs the whole chart's legibility.
        floor = low - span * 0.35
        ceiling = high + span * 0.35
        return [
            zone
            for zone in self._zones
            if zone.valid and not zone.broken and zone.high >= floor and zone.low <= ceiling
        ]


class Sparkline(QWidget):
    """A compact closing-price line. Answers direction and nothing else.

    Three things beyond a plain polyline, each earning its pixels:

    A **soft area fill** under the trace. It costs nothing to draw and it is
    what lets the eye read the shape at 26 pixels tall — a bare 1.6px line in a
    dense list reads as texture rather than as a curve.

    A **dot at the newest end**, so the direction of time is unambiguous. In a
    right-to-left interface the chart deliberately does not mirror (a mirrored
    uptrend looks like a downtrend to anybody who has seen a chart), which
    means the reader needs something other than reading order to tell them
    which end is now.

    A **baseline at the first value**, so "up" and "down" are relative to
    where the window opened rather than to the bottom of the box.
    """

    def __init__(self, parent=None, width: int = 96, height: int = 28):
        super().__init__(parent)
        self._values: list[float] = []
        self.setFixedSize(width, height)

    def set(self, values: list[float]) -> None:
        self._values = values[-60:] if values else []
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if len(self._values) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        low, high = min(self._values), max(self._values)
        span = (high - low) or 1.0
        step = self.width() / (len(self._values) - 1)
        top, bottom = 3.0, self.height() - 3.0
        usable = bottom - top

        def y_for(value: float) -> float:
            return bottom - (value - low) / span * usable

        path = QPainterPath()
        for index, value in enumerate(self._values):
            point = QPointF(index * step, y_for(value))
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)

        rising = self._values[-1] >= self._values[0]
        colour = QColor(PALETTE.ink_secondary if rising else PALETTE.ink_faint)

        # ---- area under the trace -----------------------------------------
        area = QPainterPath(path)
        area.lineTo(QPointF(self.width(), bottom))
        area.lineTo(QPointF(0.0, bottom))
        area.closeSubpath()
        fill = QColor(colour)
        fill.setAlpha(28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawPath(area)

        # ---- the baseline it is measured from ------------------------------
        baseline = QPen(QColor(PALETTE.border_strong), 1.0, Qt.PenStyle.DotLine)
        painter.setPen(baseline)
        start_y = y_for(self._values[0])
        painter.drawLine(QPointF(0.0, start_y), QPointF(float(self.width()), start_y))

        # ---- the trace -----------------------------------------------------
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(colour, 1.6))
        painter.drawPath(path)

        # ---- which end is now ----------------------------------------------
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawEllipse(
            QPointF(self.width() - 1.0, y_for(self._values[-1])), 2.2, 2.2
        )
        painter.end()


def direction_of(direction: Direction) -> int:
    return int(direction)
