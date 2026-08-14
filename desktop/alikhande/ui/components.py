"""The component library.

Every piece the views are built from. None of these know anything about the
scanner's domain — they take strings, numbers and colours — which is what keeps
a change to how a signal is scored from rippling into how a card is drawn.

Two components carry rules from the visualization method rather than taste:

``StatusChip``
    Takes ``icon`` and ``label`` as **required** positional arguments. Status
    colour must never carry meaning alone: warning and serious sit in the same
    warm family by design, and a colour-blind operator reading an amber dot with
    no text learns nothing. Making them required means a caller cannot
    accidentally ship a bare coloured dot.

``ScoreRing``
    A magnitude, so it uses the sequential blue ramp and always prints the
    number. The ring is the glanceable layer; the digits are the actual value.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..i18n import fmt_count, t
from .icons import paint_dot, paint_icon
from .motion import Pulse, Tween
from .theme import PALETTE, RADIUS, RADIUS_PILL, SPACE, TYPE, score_ramp


# --------------------------------------------------------------------- text
def label(text: str, role: str = "Body", colour: str | None = None) -> QLabel:
    """A styled label. ``role`` selects a type-scale object name."""
    widget = QLabel(text)
    widget.setObjectName(role)
    if colour:
        widget.setStyleSheet(f"color: {colour};")
    return widget


def spacer(vertical: bool = False) -> QWidget:
    widget = QWidget()
    widget.setSizePolicy(
        QSizePolicy.Policy.Minimum if vertical else QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding if vertical else QSizePolicy.Policy.Minimum,
    )
    return widget


def rule() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {PALETTE.border}; border: none;")
    return line


# -------------------------------------------------------------------- cards
class Card(QFrame):
    """A panel. ``title`` is optional — an untitled card is just a surface."""

    def __init__(self, title: str = "", quiet: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CardQuiet" if quiet else "Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(SPACE.lg + 2, SPACE.lg, SPACE.lg + 2, SPACE.lg)
        self._layout.setSpacing(SPACE.md)
        if title:
            self._layout.addWidget(label(title.upper(), "CardTitle"))

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        """Add a child. Pass ``stretch=1`` for the one child that should absorb
        spare height — without it Qt spreads the slack evenly and a table floats
        below a gap instead of filling its card."""
        self._layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout, stretch: int = 0):
        self._layout.addLayout(layout, stretch)
        return layout


# -------------------------------------------------------------------- chips
class StatusChip(QFrame):
    """An icon, a label and a colour — in that order of importance.

    The icon and label are required. Status colour is never the only channel:
    warning and serious are the same warm family by design, so hue alone cannot
    separate them, and a bare coloured dot tells a colour-blind reader nothing.
    """

    @staticmethod
    def tones() -> dict[str, tuple[str, str]]:
        """Built per call, not held as a class constant.

        ``PALETTE`` is a proxy onto whichever theme is active, so a dict built
        once at class-definition time would freeze the colours of whichever
        theme happened to be loaded when this module was first imported — and
        every chip would keep the old palette across a light/dark switch while
        the rest of the window changed.
        """
        return {
            "good": (PALETTE.good, PALETTE.good_wash),
            "warning": (PALETTE.warning, PALETTE.warning_wash),
            "serious": (PALETTE.serious, PALETTE.serious_wash),
            "critical": (PALETTE.critical, PALETTE.critical_wash),
            # Unknown is the absence of a status, not a mild one. It gets
            # neutral grey so it can never read as "slightly concerning" when
            # the truth is "nobody looked".
            "unknown": (PALETTE.unknown, PALETTE.unknown_wash),
            "neutral": (PALETTE.ink_secondary, "transparent"),
        }

    def __init__(self, icon: str, text: str, tone: str = "neutral", parent=None):
        super().__init__(parent)
        # A unique object name so the border selector below binds to THIS frame.
        # QLabel is itself a QFrame subclass, so an unscoped `QFrame { border }`
        # rule paints a box around the icon and the text as well — which is how
        # a chip ends up looking like three chips.
        self.setObjectName("StatusChip")
        # A chip hugs its text. Without this it expands to fill whatever layout
        # it lands in and stops looking like a chip at all.
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE.sm + 2, 4, SPACE.sm + 2, 4)
        row.setSpacing(6)
        self._icon = QLabel(icon)
        self._text = QLabel(text)
        row.addWidget(self._icon)
        row.addWidget(self._text, 1)
        self.set(icon, text, tone)

    def set(self, icon: str, text: str, tone: str = "neutral") -> None:
        tones = self.tones()
        colour, wash = tones.get(tone, tones["neutral"])
        self._icon.setText(icon)
        self._text.setText(text)
        self._icon.setStyleSheet(
            f"font-size: {TYPE.small}px; color: {colour}; border: none; background: transparent;"
        )
        self._text.setStyleSheet(
            f"font-size: {TYPE.small}px; font-weight: 600; color: {colour};"
            " border: none; background: transparent;"
        )
        self.setToolTip(text)
        border = "transparent" if wash == "transparent" else colour
        self.setStyleSheet(
            f"QFrame#StatusChip {{ background: {wash}; border: 1px solid {border};"
            f" border-radius: {RADIUS_PILL}px; }}"
        )


class DirectionBadge(QLabel):
    """BUY / SELL. Identity, so it takes the two direction tints.

    Always spells the word out, and in the operator's own language. Blue and
    amber are far apart under every CVD simulation, but the text is what makes
    it unambiguous under a photocopier, a screenshot, or a colleague's odd
    monitor — and a Persian reader should not have to translate the one word on
    screen that says which way the trade goes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(74)
        self.set(0)

    def set(self, direction: int) -> None:
        if direction > 0:
            text, colour, wash = t("dir.long"), PALETTE.long, PALETTE.long_wash
        elif direction < 0:
            text, colour, wash = t("dir.short"), PALETTE.short, PALETTE.short_wash
        else:
            text, colour, wash = "—", PALETTE.ink_faint, "transparent"
        self.setText(text)
        border = "transparent" if wash == "transparent" else colour
        self.setStyleSheet(
            f"background: {wash}; color: {colour}; border: 1px solid {border};"
            f" border-radius: {RADIUS_PILL}px; padding: 3px 12px;"
            f" font-size: {TYPE.small}px; font-weight: 700; letter-spacing: 0.6px;"
        )


# --------------------------------------------------------------- stat tiles
class StatTile(Card):
    """A headline number with a label and a caption.

    Not a chart. A single value's job is to be read instantly, and wrapping it
    in a plot only adds ink between the reader and the number.
    """

    def __init__(self, title: str, value: str = "—", caption: str = "", parent=None):
        super().__init__(title, parent=parent)
        self._value = label(value, "Display")
        self._caption = label(caption, "Caption")
        self._caption.setWordWrap(True)
        self._layout.addWidget(self._value)
        self._layout.addWidget(self._caption)
        self._layout.addStretch(1)

    def set(self, value: str, caption: str = "", colour: str | None = None) -> None:
        self._value.setText(value)
        self._caption.setText(caption)
        self._value.setStyleSheet(f"color: {colour};" if colour else "")


# ------------------------------------------------------------- key / value
class KeyValue(QWidget):
    """A two-column list. Values are monospaced so digits line up vertically."""

    def __init__(self, key_width: int = 132, parent=None):
        super().__init__(parent)
        self._key_width = key_width
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(SPACE.sm)
        self._rows: dict[str, QLabel] = {}

    def row(self, key: str, value: str = "—", mono: bool = True) -> None:
        """Add a row. ``mono=False`` for values that are prose rather than data.

        The monospace face exists so digits line up down the column, and for a
        price or a count that is exactly right. For a *word* it is wrong, and in
        Persian it is worse than wrong: the bundled monospace fonts have no
        Arabic-script coverage, so the shaper falls back per glyph and the text
        renders unjoined — "خاموش" came out as "خا موش". A value that is a
        sentence gets the body face.
        """
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(SPACE.md)

        name = label(key, "Caption")
        name.setFixedWidth(self._key_width)
        name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        value_label = QLabel(value)
        value_label.setObjectName("Mono" if mono else "Body")
        value_label.setWordWrap(True)
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )

        line.addWidget(name)
        line.addStretch(1)
        line.addWidget(value_label, 1)

        holder = QWidget()
        holder.setLayout(line)
        self._column.addWidget(holder)
        self._rows[key] = value_label

    def set(self, key: str, value: str, colour: str | None = None) -> None:
        widget = self._rows.get(key)
        if widget is None:
            return
        widget.setText(value)
        widget.setStyleSheet(f"color: {colour};" if colour else "")

    def clear(self) -> None:
        """Drop every row.

        Needed by lists whose *keys* change rather than only their values — the
        robot's session windows, the backup list — where ``set`` cannot help
        because the row it would update may no longer belong there.
        """
        while self._column.count():
            item = self._column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()

    def stretch(self) -> None:
        self._column.addStretch(1)


# -------------------------------------------------------------- empty state
class EmptyState(QWidget):
    """What to show when there is nothing to show.

    A row of em-dashes is not an empty state — it tells the operator that
    something is missing without telling them what or why. This says which of
    the two it is: nothing found, or not ready yet.
    """

    def __init__(self, icon: str, headline: str, detail: str = "", parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(SPACE.xl, SPACE.xxl, SPACE.xl, SPACE.xxl)
        column.setSpacing(SPACE.sm)
        column.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon = QLabel(icon)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet(f"font-size: 30px; color: {PALETTE.ink_faint};")

        self._headline = label(headline, "H3")
        self._headline.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._detail = label(detail, "Caption")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        self._detail.setMaximumWidth(520)
        self._detail.setMinimumHeight(84)
        self._detail.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )

        column.addWidget(self._icon)
        column.addWidget(self._headline)
        column.addWidget(self._detail, 0, Qt.AlignmentFlag.AlignCenter)

    def set(self, icon: str, headline: str, detail: str = "") -> None:
        self._icon.setText(icon)
        self._headline.setText(headline)
        self._detail.setText(detail)


# --------------------------------------------------------------- score ring
class ScoreRing(QWidget):
    """A circular gauge for the rule score, with the number printed inside.

    Magnitude, so: one hue, sequential, darkening with value. The ring gives the
    glance; the digits give the value. A gauge without its number is decoration.
    """

    def __init__(self, threshold: float = 75.0, diameter: int = 78, parent=None):
        super().__init__(parent)
        self._threshold = threshold
        self._score = 0.0
        self._caption = "score"
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)

    def set(self, score: float, caption: str = "score") -> None:
        self._score = max(0.0, min(100.0, score))
        self._caption = caption
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(self._diameter, self._diameter)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        thickness = 6
        inset = thickness / 2 + 1
        box = QRectF(inset, inset, self.width() - 2 * inset, self.height() - 2 * inset)

        # Track. Recessive, so the filled arc is what the eye picks up.
        painter.setPen(QPen(QColor(PALETTE.grid), thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(box, 0, 360 * 16)

        if self._score > 0:
            painter.setPen(
                QPen(
                    QColor(score_ramp(self._score, self._threshold)),
                    thickness,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            # From 12 o'clock, clockwise, so it reads as a filling dial.
            painter.drawArc(box, 90 * 16, -int(360 * 16 * self._score / 100.0))

        # A hairline at the threshold: the score's meaning is relative to it,
        # and without the mark the reader has to remember what it is.
        angle = 90.0 - 360.0 * self._threshold / 100.0
        painter.setPen(QPen(QColor(PALETTE.ink_faint), 1))
        painter.save()
        painter.translate(self.width() / 2.0, self.height() / 2.0)
        painter.rotate(-angle)
        radius = box.width() / 2.0
        painter.drawLine(int(radius - thickness - 1), 0, int(radius + 2), 0)
        painter.restore()

        # The number is the value; the ring is only the glance. Both are drawn
        # inside the ring, stacked, with the digits taking the optical centre.
        digits_height = int(self._diameter * 0.34)
        painter.setPen(QColor(PALETTE.ink))
        font = painter.font()
        font.setPixelSize(digits_height)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        centre = self.height() / 2.0
        painter.drawText(
            QRectF(0, centre - digits_height * 0.78, self.width(), digits_height * 1.1),
            int(Qt.AlignmentFlag.AlignCenter),
            f"{self._score:.0f}",
        )

        painter.setPen(QColor(PALETTE.ink_faint))
        font.setPixelSize(TYPE.micro - 1)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, centre + digits_height * 0.34, self.width(), 14),
            int(Qt.AlignmentFlag.AlignCenter),
            self._caption,
        )
        painter.end()


# ------------------------------------------------------------ bar breakdown
class BarBreakdown(QWidget):
    """Horizontal bars for the score components.

    A table of numbers makes the reader do the comparison; bars do it for them.
    Thin marks, 4px rounded ends anchored to a shared zero baseline, so positive
    and negative contributions are directly comparable.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[tuple[str, float]] = []
        self.setMinimumHeight(120)

    def set(self, items: list[tuple[str, float]]) -> None:
        self._items = list(items)
        self.setMinimumHeight(max(120, len(self._items) * 28 + 12))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont(PALETTE.font.split(",")[0].strip("'"), -1))

        if not self._items:
            painter.setPen(QColor(PALETTE.ink_faint))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No contributions — this symbol has no qualifying side.",
            )
            painter.end()
            return

        metrics = QFontMetrics(painter.font())
        name_width = min(190, max(metrics.horizontalAdvance(n) for n, _ in self._items) + 14)
        value_width = 46
        row_height = 26
        gap = 2

        zero_x = name_width + SPACE.md
        plot_width = max(40, self.width() - zero_x - value_width - SPACE.md)
        # A shared scale across all rows; per-row scaling would make a +5 and a
        # +25 draw the same length, which is the point of the chart undone.
        largest = max(abs(v) for _, v in self._items) or 1.0
        has_negative = any(v < 0 for _, v in self._items)
        # Negative contributions need room to the left of zero.
        negative_room = plot_width * 0.30 if has_negative else 0.0
        zero_x += negative_room
        positive_room = plot_width - negative_room

        for index, (name, value) in enumerate(self._items):
            top = index * row_height
            centre = top + row_height / 2.0

            painter.setPen(QColor(PALETTE.ink_secondary))
            painter.drawText(
                QRectF(0, top, name_width, row_height),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(name, Qt.TextElideMode.ElideRight, int(name_width)),
            )

            span = (positive_room if value >= 0 else negative_room) * abs(value) / largest
            span = max(span, 2.0)
            bar = QRectF(
                zero_x if value >= 0 else zero_x - span,
                centre - 5,
                span,
                10,
            )
            path = QPainterPath()
            path.addRoundedRect(bar, 4, 4)
            painter.fillPath(path, QColor(PALETTE.long if value >= 0 else PALETTE.short))

            painter.setPen(QColor(PALETTE.ink))
            painter.drawText(
                QRectF(self.width() - value_width, top, value_width, row_height),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                f"{value:+.0f}",
            )

        # The zero baseline, drawn once and recessive.
        painter.setPen(QPen(QColor(PALETTE.axis), 1))
        painter.drawLine(
            int(zero_x), 0, int(zero_x), int(len(self._items) * row_height - gap)
        )
        painter.end()


# --------------------------------------------------------------- risk meter
class RiskMeter(QWidget):
    """A horizontal gauge with a hard cap marked on it.

    Exposure only means something relative to its limit, so the limit is drawn
    rather than written somewhere else on the page.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._cap = 1.0
        self._unbounded = False
        self.setFixedHeight(30)

    def set(self, value: float, cap: float, unbounded: bool = False) -> None:
        self._value = max(0.0, value)
        self._cap = max(0.0001, cap)
        self._unbounded = unbounded
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = QRectF(0, 11, self.width(), 8)
        path = QPainterPath()
        path.addRoundedRect(track, 4, 4)
        painter.fillPath(path, QColor(PALETTE.grid))

        # Scale so the cap sits at 75% of the width: an exposure that has
        # breached its limit must still be drawable, and a bar pinned at the
        # right edge cannot show by how much.
        scale = self.width() * 0.75 / self._cap
        filled = min(self.width(), self._value * scale)

        if self._unbounded:
            # Exposure is a lower bound, so a solid bar would overstate what is
            # known. Hatching says "at least this much".
            colour = QColor(PALETTE.critical)
            painter.setPen(QPen(colour, 2))
            step = 7
            x = 0
            while x < max(filled, 12):
                painter.drawLine(int(x), 19, int(x + 5), 11)
                x += step
        elif filled > 0:
            over = self._value > self._cap
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(0, 11, max(filled, 6), 8), 4, 4)
            painter.fillPath(fill, QColor(PALETTE.critical if over else PALETTE.accent))

        cap_x = self.width() * 0.75
        painter.setPen(QPen(QColor(PALETTE.ink_muted), 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(cap_x), 4, int(cap_x), 26)
        painter.setPen(QColor(PALETTE.ink_faint))
        font = painter.font()
        font.setPixelSize(TYPE.micro)
        painter.setFont(font)
        painter.drawText(
            QRectF(cap_x + 4, 0, 70, 12),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            "cap",
        )
        painter.end()


# ------------------------------------------------------------- nav / shell
class NavItem(QPushButton):
    """One row in the sidebar: an active indicator, a vector icon, a label,
    and an optional count badge.

    Painted rather than composed from a text label with a glyph prefix. Three
    things that were not previously possible follow from that:

    * the icon takes its own colour, so it can recede while the label stays
      readable — the reverse of what a single styled string can do;
    * the **active indicator is a separate bar**, drawn in the leading margin.
      Carrying selection in a ``border-left`` shifts the label three pixels
      every time the selection moves, which is the kind of jitter nobody
      consciously notices and everybody feels;
    * the badge sits at the trailing edge at a fixed position instead of
      appended to the text, so a count appearing does not re-centre the label.

    The indicator's height is animated, so selection slides open rather than
    snapping. It is the only motion in the sidebar and it is what makes a rail
    feel like an application rather than a list of links.
    """

    def __init__(self, name: str, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("NavItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._name = name
        self._text = text
        self._badge = 0
        self._indicator = Tween(self, start=0.0)
        self._indicator.changed.connect(lambda _: self.update())
        self.toggled.connect(self._on_toggled)

    # ------------------------------------------------------------------ state
    def _on_toggled(self, checked: bool) -> None:
        self._indicator.to(1.0 if checked else 0.0)

    def set_badge(self, count: int) -> None:
        if count != self._badge:
            self._badge = count
            self.update()

    def relabel(self, name: str, text: str) -> None:
        """Change the label without losing the badge — used on a language switch."""
        self._name, self._text = name, text
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(200, 38)

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # The stylesheet still paints the background, hover and checked states.
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft

        checked = self.isChecked()
        icon_colour = PALETTE.ink if checked else PALETTE.ink_muted
        text_colour = PALETTE.ink if checked else PALETTE.ink_muted

        # ---- active indicator, in the leading margin ---------------------
        strength = self._indicator.value
        if strength > 0.01:
            full = rect.height() * 0.52
            height = full * strength
            bar = QRectF(0, 0, 3.0, height)
            bar.moveCenter(QPointF(0, rect.center().y()))
            bar.moveLeft(rect.right() - 3.0 if rtl else 0.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(PALETTE.accent))
            painter.drawRoundedRect(bar, 1.5, 1.5)

        # ---- icon ---------------------------------------------------------
        box = 18.0
        pad = SPACE.md
        if rtl:
            icon_rect = QRectF(rect.right() - pad - box, rect.center().y() - box / 2, box, box)
        else:
            icon_rect = QRectF(pad, rect.center().y() - box / 2, box, box)
        paint_icon(painter, self._name, icon_rect, icon_colour, width=1.6)

        # ---- badge, at the trailing edge -----------------------------------
        badge_width = 0.0
        if self._badge > 0:
            text = fmt_count(self._badge)
            font = QFont(self.font())
            font.setPixelSize(TYPE.micro)
            font.setWeight(QFont.Weight.Bold)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            badge_width = max(20.0, metrics.horizontalAdvance(text) + 12.0)
            pill = QRectF(0, 0, badge_width, 17.0)
            pill.moveCenter(QPointF(0, rect.center().y()))
            pill.moveLeft(pad if rtl else rect.right() - pad - badge_width)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(PALETTE.accent))
            painter.drawRoundedRect(pill, 8.5, 8.5)
            painter.setPen(QColor(PALETTE.accent_ink))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
            badge_width += SPACE.sm

        # ---- label ----------------------------------------------------------
        font = QFont(self.font())
        font.setPixelSize(TYPE.body)
        font.setWeight(QFont.Weight.DemiBold if checked else QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor(text_colour))
        text_left = pad + box + SPACE.md
        label_rect = QRectF(
            pad + badge_width if rtl else text_left,
            rect.top(),
            rect.width() - text_left - pad - badge_width,
            rect.height(),
        )
        alignment = (
            Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        ) | Qt.AlignmentFlag.AlignVCenter
        painter.drawText(label_rect, alignment, self._text)
        painter.end()


class LiveDot(QWidget):
    """A pulsing dot that says the application is doing something.

    Unattended software has one recurring credibility problem: a screen that
    shows nothing changing is indistinguishable from a screen whose process
    died twenty minutes ago. This is the cheapest possible fix and it is worth
    the pixels.

    The pulse is a smooth two-second ramp rather than a blink, because a hard
    on/off at one hertz reads as an alarm — and the ramp never reaches zero, so
    the dot does not appear to vanish in a screenshot.
    """

    def __init__(self, parent=None, diameter: int = 8):
        super().__init__(parent)
        self._diameter = diameter
        self._colour = PALETTE.good
        self._strength = 1.0
        self.setFixedSize(diameter + 4, diameter + 4)
        self._pulse = Pulse(self)
        self._pulse.changed.connect(self._on_pulse)

    def _on_pulse(self, value: float) -> None:
        # 0.45 floor: a live indicator that fades to nothing is a dead one for
        # as long as it is dark.
        self._strength = 0.45 + 0.55 * value
        self.update()

    def set_state(self, colour: str, live: bool) -> None:
        self._colour = colour
        if live:
            self._pulse.start()
        else:
            self._pulse.stop()
            self._strength = 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        centre = QPointF(self.width() / 2, self.height() / 2)
        # A soft halo under the dot. It is what makes the pulse read as light
        # rather than as the dot changing size.
        paint_dot(painter, centre, self._diameter / 2 + 2.5, self._colour, 0.18 * self._strength)
        paint_dot(painter, centre, self._diameter / 2, self._colour, self._strength)
        painter.end()


class EnvironmentPill(QFrame):
    """Which of the three environments this session is in.

    Given permanent space at the top of the window rather than being folded
    into the status bar, because it is the one fact that changes what every
    other number on screen *means*. A drawdown from a replay and a drawdown
    from a live demo account render identically and are not the same claim, and
    an operator who has to remember which they are looking at will eventually
    remember wrong.

    Production is drawn differently from the other two on purpose: a solid
    filled pill rather than an outlined one, so it is impossible to be in
    production and not notice. The lock is stated in the same breath — the pill
    reads "PRODUCTION · LOCKED", never just "PRODUCTION", because the word on
    its own invites exactly the wrong inference about what the app will do
    next.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EnvPill")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE.md, 5, SPACE.md, 5)
        row.setSpacing(SPACE.sm)
        self._text = QLabel("")
        row.addWidget(self._text)
        self.set("DEMO", locked=False)

    def set(self, environment: str, *, locked: bool) -> None:
        from ..core.environment import Environment

        if environment == Environment.PRODUCTION:
            caption = f'{t("env.production")} · {t("env.locked")}'
            colour, background, border = PALETTE.accent_ink, PALETTE.critical, PALETTE.critical
        elif environment == Environment.BACKTEST:
            caption = t("env.backtest")
            colour, background, border = (
                PALETTE.ink_secondary,
                PALETTE.unknown_wash,
                PALETTE.border_strong,
            )
        else:
            caption = t("env.demo")
            if locked:
                caption = f'{caption} · {t("env.locked")}'
            colour, background, border = PALETTE.good, PALETTE.good_wash, PALETTE.good

        self._text.setText(caption.upper())
        self._text.setStyleSheet(
            f"font-size: {TYPE.micro}px; font-weight: 800; letter-spacing: 1.1px;"
            f" color: {colour}; background: transparent; border: none;"
        )
        self.setStyleSheet(
            f"QFrame#EnvPill {{ background: {background}; border: 1px solid {border};"
            f" border-radius: {RADIUS_PILL}px; }}"
        )
        self.setToolTip(caption)


def elevate(widget: QWidget, radius: int = 22, alpha: int = 90) -> QWidget:
    """A soft shadow. Used sparingly — only the one surface asking for attention."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(radius)
    effect.setOffset(0, 3)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)
    return widget
