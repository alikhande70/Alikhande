"""Vector icons, drawn rather than typed.

The previous build used Unicode geometric characters — ``◎ ◈ ◉ ◔ ◆ ▤ ◇`` — as
navigation icons. They were placeholders that shipped, and they had three
problems worth fixing rather than tolerating:

They are not icons. ``◔`` does not mean "risk" to anybody; the glyphs were
chosen for being roughly the same visual weight, which is the only property
they actually shared.

They render differently on every machine. Each comes from whichever installed
font happens to cover that codepoint, so the sidebar's optical rhythm depends
on the operator's font stack — and on a machine missing one, a nav row shows a
replacement box.

They cannot take a colour or a weight independent of their label, because they
*are* the label as far as Qt is concerned.

So they are painted here instead: a 24×24 coordinate grid, stroked paths, one
line width, scaled to whatever the caller asks for. Stroke-only and
geometrically plain, because an icon in a 20px nav row that carries any detail
at all turns into a smudge — and the label beside it is doing the real work of
naming the destination anyway.

The one visual rule: every icon is drawn inside a 24×24 box with a 2-unit
margin, so their optical sizes agree without per-icon fudging.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

#: The grid every path below is drawn on.
GRID = 24.0


def _radar(path: QPainterPath) -> None:
    """Scanner: concentric arcs and a sweep line."""
    path.addEllipse(QRectF(3, 3, 18, 18))
    path.addEllipse(QRectF(8, 8, 8, 8))
    path.moveTo(12, 12)
    path.lineTo(19, 7)


def _grid(path: QPainterPath) -> None:
    """Dashboard: four panes, one wider — a layout, not a table."""
    path.addRoundedRect(QRectF(3, 3, 7.5, 7.5), 1.5, 1.5)
    path.addRoundedRect(QRectF(13.5, 3, 7.5, 7.5), 1.5, 1.5)
    path.addRoundedRect(QRectF(3, 13.5, 7.5, 7.5), 1.5, 1.5)
    path.addRoundedRect(QRectF(13.5, 13.5, 7.5, 7.5), 1.5, 1.5)


def _pulse(path: QPainterPath) -> None:
    """Signal: a waveform with one spike."""
    path.moveTo(2.5, 12)
    path.lineTo(7, 12)
    path.lineTo(9.5, 5)
    path.lineTo(13, 19)
    path.lineTo(15.5, 12)
    path.lineTo(21.5, 12)


def _shield(path: QPainterPath) -> None:
    """Risk: a shield outline."""
    path.moveTo(12, 2.5)
    path.lineTo(20, 6)
    path.lineTo(20, 12)
    path.cubicTo(20, 17, 16.5, 20, 12, 21.5)
    path.cubicTo(7.5, 20, 4, 17, 4, 12)
    path.lineTo(4, 6)
    path.closeSubpath()


def _target(path: QPainterPath) -> None:
    """Execution: an arrow arriving at a target."""
    path.addEllipse(QRectF(4, 4, 16, 16))
    path.addEllipse(QRectF(9.5, 9.5, 5, 5))
    path.moveTo(19, 5)
    path.lineTo(13.5, 10.5)


def _replay(path: QPainterPath) -> None:
    """Backtest: a clock face with a counter-clockwise arrow."""
    path.moveTo(4, 9)
    path.lineTo(4, 4)
    path.moveTo(4, 9)
    path.lineTo(9, 9)
    path.arcMoveTo(QRectF(3.5, 3.5, 17, 17), 150)
    path.arcTo(QRectF(3.5, 3.5, 17, 17), 150, -310)
    path.moveTo(12, 8)
    path.lineTo(12, 12.5)
    path.lineTo(15.5, 14.5)


def _heart(path: QPainterPath) -> None:
    """Health: an ECG trace inside a rounded frame."""
    path.addRoundedRect(QRectF(2.5, 4.5, 19, 15), 3, 3)
    path.moveTo(5.5, 12)
    path.lineTo(9, 12)
    path.lineTo(10.5, 8.5)
    path.lineTo(13, 15.5)
    path.lineTo(14.5, 12)
    path.lineTo(18.5, 12)


def _chip(path: QPainterPath) -> None:
    """Robot: a processor — legs on all four sides, a core in the middle."""
    path.addRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
    path.addRect(QRectF(10, 10, 4, 4))
    for offset in (9.5, 14.5):
        path.moveTo(offset, 6)
        path.lineTo(offset, 3)
        path.moveTo(offset, 18)
        path.lineTo(offset, 21)
        path.moveTo(6, offset)
        path.lineTo(3, offset)
        path.moveTo(18, offset)
        path.lineTo(21, offset)


def _journal(path: QPainterPath) -> None:
    """Journal: ruled lines with a spine."""
    path.addRoundedRect(QRectF(4, 3, 16, 18), 2, 2)
    path.moveTo(8, 3)
    path.lineTo(8, 21)
    for y in (8, 12, 16):
        path.moveTo(11, y)
        path.lineTo(17, y)


def _bars(path: QPainterPath) -> None:
    """Reports: three columns and a baseline."""
    path.moveTo(3.5, 20.5)
    path.lineTo(20.5, 20.5)
    path.addRect(QRectF(6, 12, 3.5, 8.5))
    path.addRect(QRectF(11.5, 7, 3.5, 13.5))
    path.addRect(QRectF(17, 15, 3.5, 5.5))


def _gear(path: QPainterPath) -> None:
    """Settings: a ring with teeth, drawn as spokes so it stays legible small."""
    path.addEllipse(QRectF(8.5, 8.5, 7, 7))
    path.addEllipse(QRectF(3.5, 3.5, 17, 17))
    for x, y in ((12, 2), (12, 22), (2, 12), (22, 12)):
        cx, cy = 12, 12
        dx, dy = (x - cx) * 0.24, (y - cy) * 0.24
        path.moveTo(cx + dx * 2.6, cy + dy * 2.6)
        path.lineTo(x, y)


def _wrench(path: QPainterPath) -> None:
    """Diagnostics: a spanner."""
    path.moveTo(15.5, 4)
    path.cubicTo(18.5, 3, 21, 5.5, 20, 8.5)
    path.lineTo(17, 11.5)
    path.lineTo(12.5, 7)
    path.closeSubpath()
    path.moveTo(12.5, 11.5)
    path.lineTo(5, 19)
    path.cubicTo(4, 20, 5.5, 21.5, 6.5, 20.5)
    path.lineTo(14, 13)


def _question(path: QPainterPath) -> None:
    """Guide: a question mark in a circle."""
    path.addEllipse(QRectF(3, 3, 18, 18))
    path.arcMoveTo(QRectF(9, 7, 6, 6), 200)
    path.arcTo(QRectF(9, 7, 6, 6), 200, -230)
    path.lineTo(12, 14.5)
    path.moveTo(12, 17.5)
    path.lineTo(12.01, 17.5)


def _bell(path: QPainterPath) -> None:
    """Notifications."""
    path.moveTo(6, 17)
    path.lineTo(6, 11)
    path.cubicTo(6, 7, 8.5, 4.5, 12, 4.5)
    path.cubicTo(15.5, 4.5, 18, 7, 18, 11)
    path.lineTo(18, 17)
    path.closeSubpath()
    path.moveTo(4, 17)
    path.lineTo(20, 17)
    path.moveTo(10, 20)
    path.cubicTo(10.5, 21.5, 13.5, 21.5, 14, 20)


#: Name to path builder. A missing name draws nothing rather than raising —
#: an icon is decoration on top of a text label that already names the
#: destination, and a crash over one is out of all proportion.
BUILDERS = {
    "scanner": _radar,
    "dashboard": _grid,
    "signal": _pulse,
    "risk": _shield,
    "execution": _target,
    "backtest": _replay,
    "health": _heart,
    "robot": _chip,
    "journal": _journal,
    "reports": _bars,
    "settings": _gear,
    "diagnostics": _wrench,
    "guide": _question,
    "notifications": _bell,
}


def icon_path(name: str) -> QPainterPath:
    path = QPainterPath()
    builder = BUILDERS.get(name)
    if builder is not None:
        builder(path)
    return path


def paint_icon(
    painter: QPainter,
    name: str,
    rect: QRectF,
    colour: str,
    *,
    width: float = 1.6,
    opacity: float = 1.0,
) -> None:
    """Stroke ``name`` inside ``rect``.

    The pen is set to a cosmetic-ish width scaled by the box, so a 16px icon
    and a 24px icon have the same *optical* weight rather than the same
    absolute stroke — the latter makes small icons look spindly and large ones
    look clumsy.
    """
    path = icon_path(name)
    if path.isEmpty():
        return

    scale = min(rect.width(), rect.height()) / GRID
    painter.save()
    painter.setOpacity(opacity)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(
        rect.center().x() - GRID * scale / 2.0, rect.center().y() - GRID * scale / 2.0
    )
    painter.scale(scale, scale)

    # The pen width is in grid units, and the painter is already scaled, so the
    # stroke scales with the icon. That is what keeps a 16px and a 24px icon at
    # the same *optical* weight — an absolute stroke makes small icons spindly
    # and large ones clumsy.
    pen = QPen(QColor(colour))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.restore()


def paint_dot(painter: QPainter, centre: QPointF, radius: float, colour: str, opacity: float = 1.0) -> None:
    """A filled dot. Used for the live indicator and status bullets."""
    painter.save()
    painter.setOpacity(opacity)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colour))
    painter.drawEllipse(centre, radius, radius)
    painter.restore()
