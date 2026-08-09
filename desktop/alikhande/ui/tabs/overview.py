"""Overview tab — the scannable one.

Design rule inherited from the MQL5 panel: this tab stays scannable and the
Detail tab carries the depth. A row here answers "is anything happening?" at a
glance; anything that needs reading belongs one tab over.

Probability is rendered through the statistics layer's formatter, never
formatted locally, so a win rate can never appear here without its sample size
and interval.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...core.enums import (
    DIRECTION_NAMES,
    SETUP_NAMES,
    SPREAD_STATE_NAMES,
    Direction,
    NewsState,
    SignalState,
    SpreadState,
)
from ...core.statistics import Statistics
from ..theme import PALETTE, score_colour
from ..widgets import Card, Metric, Table

HEADERS = [
    "Symbol",
    "Bias",
    "Setup",
    "Score",
    "Zone",
    "Entry",
    "Stop",
    "Target",
    "Lots",
    "Risk",
    "Spread",
    "News",
    "Win rate",
    "State",
]


class OverviewTab(QWidget):
    symbol_activated = Signal(str)

    def __init__(self, statistics: Statistics, threshold: float) -> None:
        super().__init__()
        self._statistics = statistics
        self._threshold = threshold

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(PALETTE.gap)

        strip = QHBoxLayout()
        strip.setSpacing(PALETTE.gap)
        self._m_scanned = Metric("Symbols", "0", "resolved on this broker")
        self._m_actionable = Metric("Actionable", "0", "confirmed with a valid plan")
        self._m_blocked = Metric("Blocked", "0", "hard-blocked this pass")
        self._m_risk = Metric("Open risk", "0.00%", "aggregate, this app only")
        for metric in (self._m_scanned, self._m_actionable, self._m_blocked, self._m_risk):
            strip.addWidget(metric)
        root.addLayout(strip)

        card = Card("Live scan")
        self._table = Table(HEADERS)
        self._table.itemDoubleClicked.connect(self._on_double_click)
        card.add(self._table, 1)
        root.addWidget(card, 1)

    def _on_double_click(self, item) -> None:
        symbol = self._table.item(item.row(), 0)
        if symbol is not None:
            self.symbol_activated.emit(symbol.text())

    def update_view(self, snapshot) -> None:
        views = snapshot.symbols
        actionable = sum(
            1 for v in views if v.plan is not None and v.plan.valid and not v.news_blocks
        )
        blocked = sum(1 for v in views if v.signal is not None and v.signal.hard_blocked)

        self._m_scanned.set(str(sum(1 for v in views if v.resolved)), "resolved on this broker")
        self._m_actionable.set(
            str(actionable),
            "confirmed with a valid plan",
            PALETTE.accent if actionable else None,
        )
        self._m_blocked.set(str(blocked), "hard-blocked this pass")
        self._m_risk.set(
            f"{snapshot.exposure_open_pct:.2f}%",
            "aggregate, this app only",
            PALETTE.warning if snapshot.exposure_open_pct > 0.75 else None,
        )

        self._table.clear_rows()
        self._table.setRowCount(len(views))

        for row, view in enumerate(views):
            digits = view.spec.digits if view.spec else 5
            signal = view.signal
            plan = view.plan

            self._table.set_cell(row, 0, view.symbol or view.requested, mono=True)

            if not view.resolved:
                self._table.set_cell(row, 1, "unresolved", PALETTE.danger)
                for column in range(2, len(HEADERS)):
                    self._table.set_cell(row, column, "—", PALETTE.text_faint)
                continue

            if signal is None:
                for column in range(1, len(HEADERS) - 1):
                    self._table.set_cell(row, column, "—", PALETTE.text_faint)
                self._table.set_cell(
                    row, len(HEADERS) - 1, view.last_error or "warming up", PALETTE.text_faint
                )
                continue

            direction_colour = {
                Direction.LONG: PALETTE.long,
                Direction.SHORT: PALETTE.short,
            }.get(signal.direction, PALETTE.text_faint)

            self._table.set_cell(
                row, 1, DIRECTION_NAMES[signal.direction], direction_colour
            )
            self._table.set_cell(
                row,
                2,
                SETUP_NAMES[signal.setup],
                PALETTE.text if signal.setup.value else PALETTE.text_faint,
            )

            score = max(signal.long_score, signal.short_score)
            self._table.set_cell(
                row, 3, f"{score:.0f}", score_colour(score, self._threshold), align_right=True
            )

            relation = (
                signal.demand_relation
                if signal.direction == Direction.LONG
                else signal.supply_relation
            )
            self._table.set_cell(
                row,
                4,
                relation.name,
                PALETTE.accent if relation.name == "INSIDE" else PALETTE.text_faint,
            )

            def price(value: float) -> str:
                return f"{value:.{digits}f}" if value > 0 else "—"

            self._table.set_cell(row, 5, price(signal.preferred_entry), mono=True, align_right=True)
            self._table.set_cell(row, 6, price(signal.stop_loss), mono=True, align_right=True)
            self._table.set_cell(row, 7, price(signal.take_profit), mono=True, align_right=True)

            if plan is not None and plan.valid:
                self._table.set_cell(row, 8, f"{plan.lot_size:.2f}", mono=True, align_right=True)
                self._table.set_cell(
                    row, 9, f"{plan.risk_percent:.2f}%", mono=True, align_right=True
                )
            else:
                reason = plan.codes_text() if plan is not None else "—"
                self._table.set_cell(row, 8, "—", PALETTE.text_faint, align_right=True)
                self._table.set_cell(
                    row, 9, reason[:22] or "—", PALETTE.text_faint, align_right=True
                )

            # WARMING_UP blocks trading but is not a fault — it is the tracker
            # honestly declining to classify a spread it has not seen enough of.
            # Colouring it as an error teaches the operator to ignore the colour
            # that does mean one.
            spread_colour = {
                SpreadState.NORMAL: PALETTE.text_dim,
                SpreadState.ELEVATED: PALETTE.warning,
                SpreadState.WARMING_UP: PALETTE.muted,
            }.get(view.snapshot.spread_state, PALETTE.danger)
            self._table.set_cell(
                row, 10, SPREAD_STATE_NAMES[view.snapshot.spread_state], spread_colour
            )

            news_colour = {
                NewsState.CLEAR: PALETTE.text_dim,
                NewsState.BLOCKED: PALETTE.danger,
                NewsState.UNKNOWN: PALETTE.muted,
            }[view.news.state]
            self._table.set_cell(row, 11, view.news.state.name, news_colour)

            # Never formatted locally. The statistics layer refuses to render a
            # rate below the sample floor, and that refusal is the point.
            self._table.set_cell(
                row,
                12,
                self._statistics.format_probability(signal),
                PALETTE.text if signal.has_historical_estimate else PALETTE.muted,
            )

            state_colour = (
                PALETTE.accent
                if signal.state in (SignalState.CONFIRMED, SignalState.PREVIEWED)
                else PALETTE.text_faint
            )
            self._table.set_cell(row, 13, signal.state.name, state_colour)

        self._table.fit_columns()
