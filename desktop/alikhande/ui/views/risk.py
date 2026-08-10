"""Risk view — exposure against its limits, and the evidence base.

Two things here that the MQL5 panel could not show because the data did not
exist: the outcome record, and the unbounded-position warning.

The evidence panel is deliberately blunt about an empty database. "No outcomes
recorded yet" is the correct and complete answer until trades resolve; rendering
it as 0% would be a fabricated statistic, which is exactly what this project
exists not to do.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.statistics import wilson
from ..components import (
    Card,
    EmptyState,
    KeyValue,
    RiskMeter,
    StatTile,
    StatusChip,
    label,
)
from ..theme import PALETTE, SPACE, TYPE, r_colour

POSITION_HEADERS = ["Symbol", "Side", "Volume", "Entry", "Stop", "Target", "P/L", "Bounded"]


class RiskView(QWidget):
    def __init__(self, config, repositories=None):
        super().__init__()
        self._config = config
        self._repo = repositories

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        page = QWidget()
        page.setObjectName("Content")
        root = QVBoxLayout(page)
        root.setContentsMargins(SPACE.xl, SPACE.lg, SPACE.xl, SPACE.xl)
        root.setSpacing(SPACE.lg)
        scroll.setWidget(page)

        tiles = QHBoxLayout()
        tiles.setSpacing(SPACE.md)
        self._tile_equity = StatTile("Equity", "—", "account currency")
        self._tile_risk = StatTile("Open risk", "0.00%", "")
        self._tile_positions = StatTile("Positions", "0", "opened by this app")
        self._tile_drawdown = StatTile("Drawdown", "0.00%", "from peak equity")
        for tile in (
            self._tile_equity,
            self._tile_risk,
            self._tile_positions,
            self._tile_drawdown,
        ):
            tiles.addWidget(tile)
        root.addLayout(tiles)

        # ---- exposure against its cap ----------------------------------------
        exposure = Card("Exposure against limits")
        self._meter_open = self._meter_row(exposure, "Aggregate open risk")
        self._meter_currency = self._meter_row(exposure, "Dominant currency leg")
        self._meter_class = self._meter_row(exposure, "Asset class")
        self._unbounded = StatusChip("✓", "ALL POSITIONS BOUNDED", "good")
        exposure.add(self._unbounded, 0)
        root.addWidget(exposure)

        columns = QHBoxLayout()
        columns.setSpacing(SPACE.md)

        policy = Card("Policy")
        self._policy = KeyValue(140)
        for key in (
            "Per-trade risk",
            "Per-trade ceiling",
            "Minimum R:R",
            "Aggregate cap",
            "Per-currency cap",
            "Asset-class cap",
            "Circuit breakers",
        ):
            self._policy.row(key)
        self._policy.stretch()
        policy.add(self._policy)
        columns.addWidget(policy, 1)

        guards = Card("Guard state")
        self._guards = KeyValue(140)
        for key in (
            "Trading permitted",
            "Breached guards",
            "Peak equity",
            "Day-start equity",
            "Consecutive losses",
            "Daily risk used",
        ):
            self._guards.row(key)
        self._guards.stretch()
        guards.add(self._guards)
        columns.addWidget(guards, 1)

        self._evidence = Card("Evidence base")
        self._evidence_body = KeyValue(140)
        for key in (
            "Resolved trades",
            "Wins / losses",
            "Win rate",
            "95% Wilson",
            "Total R",
            "Expectancy",
        ):
            self._evidence_body.row(key)
        self._evidence_body.stretch()
        self._evidence.add(self._evidence_body)
        self._evidence_empty = EmptyState(
            "◔",
            "No outcomes yet",
            "A win rate appears only after "
            f"{config.statistics.min_outcome_sample} resolved trades on the same "
            "symbol, setup and rule version. Until then there is nothing honest "
            "to show.",
        )
        self._evidence.add(self._evidence_empty)
        columns.addWidget(self._evidence, 1)

        root.addLayout(columns)

        positions = Card("Open positions")
        self._table = QTableWidget(0, len(POSITION_HEADERS))
        self._table.setHorizontalHeaderLabels(POSITION_HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(38)
        self._table.horizontalHeader().setStretchLastSection(True)
        positions.add(self._table, 1)
        self._positions_empty = EmptyState(
            "○", "No open positions", "Nothing has been opened by this application."
        )
        positions.add(self._positions_empty)
        root.addWidget(positions, 1)

        self._render_policy()

    def _meter_row(self, card: Card, name: str):
        row = QVBoxLayout()
        row.setSpacing(2)
        header = QHBoxLayout()
        title = label(name, "Caption")
        value = label("0.00% / 0.00%", "Mono")
        value.setAlignment(Qt.AlignmentFlag.AlignRight)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(value)
        meter = RiskMeter()
        row.addLayout(header)
        row.addWidget(meter)
        card.add_layout(row)
        return meter, value

    def _render_policy(self) -> None:
        risk = self._config.risk
        self._policy.set("Per-trade risk", f"{risk.risk_percent:.2f}%")
        self._policy.set("Per-trade ceiling", f"{risk.maximum_risk_percent:.2f}%  [POLICY]")
        self._policy.set("Minimum R:R", f"1 : {risk.minimum_risk_reward:.2f}  [POLICY]")
        self._policy.set("Aggregate cap", f"{risk.max_open_risk_pct:.2f}%")
        self._policy.set("Per-currency cap", f"{risk.max_currency_risk_pct:.2f}%")
        self._policy.set("Asset-class cap", f"{risk.max_asset_class_risk_pct:.2f}%")
        self._policy.set(
            "Circuit breakers",
            "enabled" if risk.guards_enabled else "disabled (default)",
            PALETTE.good if risk.guards_enabled else PALETTE.ink_muted,
        )

    # ----------------------------------------------------------------- render
    def update_view(self, snapshot, positions, exposure, guard_state) -> None:
        risk = self._config.risk
        account = snapshot.account
        equity = account.equity if account else 0.0

        self._tile_equity.set(
            f"{equity:,.0f}" if account else "—",
            account.currency if account else "no account attached",
        )
        self._tile_risk.set(
            f"{exposure.open_risk_pct:.2f}%",
            f"cap {risk.max_open_risk_pct:.2f}%",
            PALETTE.critical if exposure.open_risk_pct > risk.max_open_risk_pct else None,
        )
        self._tile_positions.set(str(exposure.open_positions), "opened by this app")

        drawdown = 0.0
        if guard_state.peak_equity > 0 and equity > 0:
            drawdown = (guard_state.peak_equity - equity) / guard_state.peak_equity * 100.0
        self._tile_drawdown.set(
            f"{drawdown:.2f}%",
            "from peak equity",
            PALETTE.critical if drawdown >= risk.total_drawdown_limit_pct else None,
        )

        unbounded = exposure.unbounded_positions > 0
        for (meter, value), current, cap in (
            (self._meter_open, exposure.open_risk_pct, risk.max_open_risk_pct),
            (self._meter_currency, exposure.currency_risk_pct, risk.max_currency_risk_pct),
            (self._meter_class, exposure.asset_class_risk_pct, risk.max_asset_class_risk_pct),
        ):
            meter.set(current, cap, unbounded)
            value.setText(f"{current:.2f}% / {cap:.2f}%")
            value.setStyleSheet(f"color: {PALETTE.critical};" if current > cap else "")

        if unbounded:
            self._unbounded.set(
                "✕",
                f"{exposure.unbounded_positions} POSITION(S) WITHOUT A COMPUTABLE WORST "
                f"CASE — every figure above is a LOWER BOUND and new risk is refused "
                f"({', '.join(exposure.unbounded_symbols)})",
                "critical",
            )
        else:
            self._unbounded.set("✓", "ALL POSITIONS BOUNDED", "good")

        self._guards.set(
            "Trading permitted",
            "yes" if snapshot.may_trade else "NO",
            PALETTE.good if snapshot.may_trade else PALETTE.critical,
        )
        self._guards.set(
            "Breached guards",
            "; ".join(snapshot.guard_codes) if snapshot.guard_codes else "none",
            PALETTE.critical if snapshot.guard_codes else PALETTE.ink_secondary,
        )
        self._guards.set("Peak equity", f"{guard_state.peak_equity:,.2f}")
        self._guards.set("Day-start equity", f"{guard_state.day_start_equity:,.2f}")
        self._guards.set("Consecutive losses", str(guard_state.consecutive_losses))
        self._guards.set("Daily risk used", f"{guard_state.daily_risk_used_pct:.2f}%")

        self._render_evidence()
        self._render_positions(positions)

    def _render_evidence(self) -> None:
        floor = self._config.statistics.min_outcome_sample

        if self._repo is None or not self._repo.ready:
            self._evidence_body.setVisible(False)
            self._evidence_empty.setVisible(True)
            self._evidence_empty.set(
                "○",
                "No database",
                "This session records nothing, so there is no evidence base to show.",
            )
            return

        summary = self._repo.outcome_summary()
        total = int(summary["total"])

        if total == 0:
            self._evidence_body.setVisible(False)
            self._evidence_empty.setVisible(True)
            self._evidence_empty.set(
                "◔",
                "No outcomes yet",
                f"A win rate appears only after {floor} resolved trades on the same "
                "symbol, setup and rule version. Until then there is nothing honest "
                "to show.",
            )
            return

        self._evidence_body.setVisible(True)
        self._evidence_empty.setVisible(False)

        wins = int(summary["wins"])
        self._evidence_body.set("Resolved trades", str(total))
        self._evidence_body.set("Wins / losses", f"{wins} / {total - wins}")
        self._evidence_body.set(
            "Total R", f"{summary['sum_r']:+.2f}", r_colour(summary["sum_r"])
        )
        self._evidence_body.set(
            "Expectancy", f"{summary['avg_r']:+.3f} R", r_colour(summary["avg_r"])
        )

        if total < floor:
            self._evidence_body.set(
                "Win rate", f"withheld — {total}/{floor}", PALETTE.ink_muted
            )
            self._evidence_body.set("95% Wilson", "—", PALETTE.ink_muted)
            return

        interval = wilson(wins, total)
        self._evidence_body.set("Win rate", f"{wins / total * 100:.1f}%")
        self._evidence_body.set(
            "95% Wilson",
            f"[{interval[0] * 100:.1f}%, {interval[1] * 100:.1f}%]" if interval else "—",
        )

    def _render_positions(self, positions) -> None:
        self._positions_empty.setVisible(not positions)
        self._table.setVisible(bool(positions))
        self._table.setRowCount(len(positions))

        for row, position in enumerate(positions):
            long = position.direction.value > 0
            bounded = position.stop_loss > 0
            cells = [
                (position.symbol, None, True, False),
                ("LONG" if long else "SHORT", PALETTE.long if long else PALETTE.short, False, False),
                (f"{position.volume:.2f}", None, True, True),
                (f"{position.price_open:.5f}", None, True, True),
                (
                    f"{position.stop_loss:.5f}" if bounded else "NONE",
                    None if bounded else PALETTE.critical,
                    True,
                    True,
                ),
                (
                    f"{position.take_profit:.5f}" if position.take_profit > 0 else "—",
                    None,
                    True,
                    True,
                ),
                (f"{position.profit:+.2f}", r_colour(position.profit), True, True),
                (
                    "bounded" if bounded else "UNBOUNDED — new risk refused",
                    PALETTE.ink_muted if bounded else PALETTE.critical,
                    False,
                    False,
                ),
            ]
            for column, (text, colour, mono, right) in enumerate(cells):
                item = QTableWidgetItem(text)
                if colour:
                    from PySide6.QtGui import QColor

                    item.setForeground(QColor(colour))
                if mono:
                    from PySide6.QtGui import QFont

                    item.setFont(QFont(PALETTE.mono.split(",")[0].strip("'"), TYPE.small))
                if right:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(row, column, item)

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)
