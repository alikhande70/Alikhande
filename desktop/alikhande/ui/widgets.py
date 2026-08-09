"""Small reusable widgets.

Nothing here knows about the scanner's domain — they take strings and colours.
The domain lives in the tabs, which is what keeps a change to how a signal is
scored from rippling into how a card is drawn.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import PALETTE


class Card(QFrame):
    """A titled panel. The building block of every tab."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 13, 16, 15)
        self._layout.setSpacing(9)

        if title:
            label = QLabel(title.upper())
            label.setObjectName("CardTitle")
            self._layout.addWidget(label)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        """Add a child. Pass ``stretch=1`` for the one child that should absorb
        spare height — without it Qt distributes the slack evenly and a table
        ends up floating below a gap instead of filling its card."""
        self._layout.addWidget(widget, stretch)
        return widget


class Metric(Card):
    """A single headline number with an optional caption underneath."""

    def __init__(self, title: str, value: str = "—", caption: str = "") -> None:
        super().__init__(title)
        self._value = QLabel(value)
        self._value.setObjectName("Metric")
        self._layout.addWidget(self._value)

        self._caption = QLabel(caption)
        self._caption.setObjectName("Caption")
        self._caption.setWordWrap(True)
        self._layout.addWidget(self._caption)
        self._layout.addStretch(1)

    def set(self, value: str, caption: str = "", colour: str | None = None) -> None:
        self._value.setText(value)
        self._caption.setText(caption)
        self._value.setStyleSheet(f"color: {colour};" if colour else "")


class Pill(QLabel):
    """A compact status chip. ``kind`` selects the styled variant."""

    def __init__(self, text: str = "", kind: str = "") -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set(text, kind)

    def set(self, text: str, kind: str = "") -> None:
        self.setText(text)
        self.setObjectName(
            {
                "ok": "PillOk",
                "warn": "PillWarn",
                "danger": "PillDanger",
            }.get(kind, "Pill")
        )
        # Qt only re-evaluates the stylesheet when the object name changes if
        # the widget is explicitly re-polished.
        self.style().unpolish(self)
        self.style().polish(self)


class KeyValue(QWidget):
    """A two-column label list. Values are monospaced so numbers line up."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QVBoxLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(5)
        self._rows: dict[str, QLabel] = {}

    def row(self, key: str, value: str = "—") -> None:
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)

        label = QLabel(key)
        label.setObjectName("Caption")
        label.setMinimumWidth(140)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        holder = QLabel(value)
        holder.setObjectName("Mono")
        holder.setWordWrap(True)
        holder.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        line.addWidget(label)
        line.addStretch(1)
        line.addWidget(holder)

        container = QWidget()
        container.setLayout(line)
        self._grid.addWidget(container)
        self._rows[key] = holder

    def set(self, key: str, value: str, colour: str | None = None) -> None:
        label = self._rows.get(key)
        if label is None:
            return
        label.setText(value)
        label.setStyleSheet(f"color: {colour};" if colour else "")

    def stretch(self) -> None:
        self._grid.addStretch(1)


class Table(QTableWidget):
    """A read-only table with sensible defaults for numeric data."""

    def __init__(self, headers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setWordWrap(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setDefaultSectionSize(34)

    def set_cell(
        self,
        row: int,
        column: int,
        text: str,
        colour: str | None = None,
        mono: bool = False,
        align_right: bool = False,
    ) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if colour:
            from PySide6.QtGui import QColor

            item.setForeground(QColor(colour))
        if mono:
            from PySide6.QtGui import QFont

            item.setFont(QFont(PALETTE.font_mono.split(",")[0].strip("'"), 10))
        if align_right:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        self.setItem(row, column, item)
        return item

    def clear_rows(self) -> None:
        self.setRowCount(0)

    def fit_columns(self) -> None:
        """Size columns to their contents, leaving the last one to fill.

        Called after every repopulation. Without it Qt keeps the default fixed
        width and silently elides — which on this panel meant a zone relation
        rendering as ``UNAVAIL…``, i.e. the one state the operator most needs to
        read clearly became the one they could not.
        """
        from PySide6.QtWidgets import QHeaderView

        header = self.horizontalHeader()
        for column in range(self.columnCount() - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            self.columnCount() - 1, QHeaderView.ResizeMode.Stretch
        )


def separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"background: {PALETTE.border}; max-height: 1px; border: none;")
    return line
