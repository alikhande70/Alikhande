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

from ...i18n import fmt_count, fmt_money, fmt_percent, fmt_price, t
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

POSITION_KEYS = ["col.symbol","col.side","col.volume","col.entry","col.stop","col.target","col.pl","col.bounded"]


class RiskView(QWidget):
    def __init__(self, config):
        super().__init__()
        self._config = config

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
        self._tile_equity = StatTile(t("risk.tile.equity"), t("common.none"))
        self._tile_risk = StatTile(t("risk.tile.risk"), "0.00%")
        self._tile_positions = StatTile(t("risk.tile.positions"), "0")
        self._tile_drawdown = StatTile(t("risk.tile.drawdown"), "0.00%")
        for tile in (
            self._tile_equity,
            self._tile_risk,
            self._tile_positions,
            self._tile_drawdown,
        ):
            tiles.addWidget(tile)
        root.addLayout(tiles)

        # ---- exposure against its cap ----------------------------------------
        exposure = Card(t("risk.exposure"))
        self._meter_open = self._meter_row(exposure, t("risk.meter.open"))
        self._meter_currency = self._meter_row(exposure, t("risk.meter.currency"))
        self._meter_class = self._meter_row(exposure, t("risk.meter.class"))
        self._unbounded = StatusChip("✓", t("risk.bounded"), "good")
        exposure.add(self._unbounded, 0)
        root.addWidget(exposure)

        columns = QHBoxLayout()
        columns.setSpacing(SPACE.md)

        policy = Card(t("risk.policy"))
        self._policy = KeyValue(140)
        for key in (
            t("policy.per_trade"),
            t("policy.ceiling"),
            t("policy.min_rr"),
            t("policy.aggregate"),
            t("policy.currency"),
            t("policy.class"),
            t("policy.breakers"),
        ):
            self._policy.row(key)
        self._policy.stretch()
        policy.add(self._policy)
        columns.addWidget(policy, 1)

        guards = Card(t("risk.guards"))
        self._guards = KeyValue(140)
        for key in (
            t("guard.permitted"),
            t("guard.breached"),
            t("guard.peak"),
            t("guard.daystart"),
            t("guard.losses"),
            t("guard.used"),
        ):
            self._guards.row(key)
        self._guards.stretch()
        guards.add(self._guards)
        columns.addWidget(guards, 1)

        self._evidence = Card(t("risk.evidence"))
        self._evidence_body = KeyValue(140)
        for key in (
            t("evidence.trades"),
            t("evidence.wins"),
            t("evidence.winrate"),
            t("evidence.wilson"),
            t("evidence.total_r"),
            t("evidence.expectancy"),
        ):
            self._evidence_body.row(key)
        self._evidence_body.stretch()
        self._evidence.add(self._evidence_body)
        self._evidence_empty = EmptyState(
            "◔",
            t("risk.no_outcomes"),
            t("risk.no_outcomes.detail", floor=fmt_count(config.statistics.min_outcome_sample)),
        )
        self._evidence.add(self._evidence_empty)
        columns.addWidget(self._evidence, 1)

        root.addLayout(columns)

        positions = Card(t("risk.positions"))
        self._table = QTableWidget(0, len(POSITION_KEYS))
        self._table.setHorizontalHeaderLabels([t(k) for k in POSITION_KEYS])
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(38)
        self._table.horizontalHeader().setStretchLastSection(True)
        positions.add(self._table, 1)
        self._positions_empty = EmptyState(
            "○", t("risk.no_positions"), t("risk.no_positions.detail")
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
        self._policy.set(t("policy.per_trade"), f"{risk.risk_percent:.2f}%")
        self._policy.set(t("policy.ceiling"), f"{risk.maximum_risk_percent:.2f}%  [POLICY]")
        self._policy.set(t("policy.min_rr"), f"1 : {risk.minimum_risk_reward:.2f}  [POLICY]")
        self._policy.set(t("policy.aggregate"), f"{risk.max_open_risk_pct:.2f}%")
        self._policy.set(t("policy.currency"), f"{risk.max_currency_risk_pct:.2f}%")
        self._policy.set(t("policy.class"), f"{risk.max_asset_class_risk_pct:.2f}%")
        self._policy.set(
            t("policy.breakers"),
            t("policy.enabled") if risk.guards_enabled else t("policy.disabled"),
            PALETTE.good if risk.guards_enabled else PALETTE.ink_muted,
        )

    # ----------------------------------------------------------------- render
    def update_view(self, snapshot, positions=None, exposure=None, guard_state=None) -> None:
        positions = snapshot.positions if positions is None else positions
        exposure = snapshot.exposure if exposure is None else exposure
        guard_state = snapshot.guard_state if guard_state is None else guard_state
        risk = self._config.risk
        account = snapshot.account
        equity = account.equity if account else 0.0
        positions_known = getattr(snapshot, "positions_known", True)

        self._tile_equity.set(
            fmt_money(equity, 0) if account else t("common.none"),
            account.currency if account else t("chip.no_account"),
        )
        if positions_known:
            self._tile_risk.set(
                fmt_percent(exposure.open_risk_pct),
                t("dash.tile.risk.caption", cap=fmt_percent(risk.max_open_risk_pct)),
                PALETTE.critical
                if exposure.open_risk_pct > risk.max_open_risk_pct
                else None,
            )
            self._tile_positions.set(
                fmt_count(exposure.open_positions), t("risk.tile.positions.caption")
            )
        else:
            self._tile_risk.set("?", t("risk.exposure.unknown"), PALETTE.critical)
            self._tile_positions.set("?", t("risk.positions.unknown"), PALETTE.critical)

        drawdown = 0.0
        if guard_state.peak_equity > 0 and equity > 0:
            drawdown = (guard_state.peak_equity - equity) / guard_state.peak_equity * 100.0
        self._tile_drawdown.set(
            fmt_percent(drawdown),
            t("risk.tile.drawdown.caption"),
            PALETTE.critical if drawdown >= risk.total_drawdown_limit_pct else None,
        )

        unbounded = exposure.unbounded_positions > 0 or not positions_known
        for (meter, value), current, cap in (
            (self._meter_open, exposure.open_risk_pct, risk.max_open_risk_pct),
            (self._meter_currency, exposure.currency_risk_pct, risk.max_currency_risk_pct),
            (self._meter_class, exposure.asset_class_risk_pct, risk.max_asset_class_risk_pct),
        ):
            meter.set(current, cap, unbounded)
            value.setText(
                f"{current:.2f}% / {cap:.2f}%"
                if positions_known
                else f"? / {cap:.2f}%"
            )
            value.setStyleSheet(
                f"color: {PALETTE.critical};"
                if not positions_known or current > cap
                else ""
            )

        if not positions_known:
            self._unbounded.set("?", t("risk.exposure.unknown"), "critical")
        elif unbounded:
            self._unbounded.set(
                "✕",
                t(
                    "risk.unbounded",
                    count=fmt_count(exposure.unbounded_positions),
                    symbols=", ".join(exposure.unbounded_symbols),
                ),
                "critical",
            )
        else:
            self._unbounded.set("✓", t("risk.bounded"), "good")

        self._guards.set(
            t("guard.permitted"),
            t("guard.yes") if snapshot.may_trade else t("guard.no"),
            PALETTE.good if snapshot.may_trade else PALETTE.critical,
        )
        self._guards.set(
            t("guard.breached"),
            "; ".join(snapshot.guard_codes) if snapshot.guard_codes else t("guard.none"),
            PALETTE.critical if snapshot.guard_codes else PALETTE.ink_secondary,
        )
        self._guards.set(t("guard.peak"), f"{guard_state.peak_equity:,.2f}")
        self._guards.set(t("guard.daystart"), f"{guard_state.day_start_equity:,.2f}")
        self._guards.set(t("guard.losses"), str(guard_state.consecutive_losses))
        self._guards.set(t("guard.used"), f"{guard_state.daily_risk_used_pct:.2f}%")

        self._render_evidence(snapshot.outcome_summary, snapshot.persistence_ready)
        self._render_positions(positions, known=positions_known)

    def _render_evidence(self, summary: dict, persistence_ready: bool) -> None:
        floor = self._config.statistics.min_outcome_sample

        if not persistence_ready:
            self._evidence_body.setVisible(False)
            self._evidence_empty.setVisible(True)
            self._evidence_empty.set(
                "○",
                t("risk.no_database"),
                t("risk.no_database.detail"),
            )
            return

        total = int(summary["total"])

        if total == 0:
            self._evidence_body.setVisible(False)
            self._evidence_empty.setVisible(True)
            self._evidence_empty.set(
                "◔",
                t("risk.no_outcomes"),
                t("risk.no_outcomes.detail", floor=fmt_count(floor)),
            )
            return

        self._evidence_body.setVisible(True)
        self._evidence_empty.setVisible(False)

        wins = int(summary["wins"])
        self._evidence_body.set(t("evidence.trades"), str(total))
        self._evidence_body.set(t("evidence.wins"), f"{wins} / {total - wins}")
        self._evidence_body.set(
            t("evidence.total_r"), f"{summary['sum_r']:+.2f}", r_colour(summary["sum_r"])
        )
        self._evidence_body.set(
            t("evidence.expectancy"), f"{summary['avg_r']:+.3f} R", r_colour(summary["avg_r"])
        )

        if total < floor:
            self._evidence_body.set(
                t("evidence.winrate"), t("evidence.withheld", count=fmt_count(total), floor=fmt_count(floor)), PALETTE.ink_muted
            )
            self._evidence_body.set(t("evidence.wilson"), "—", PALETTE.ink_muted)
            return

        interval = wilson(wins, total)
        self._evidence_body.set(t("evidence.winrate"), f"{wins / total * 100:.1f}%")
        self._evidence_body.set(
            t("evidence.wilson"),
            f"[{interval[0] * 100:.1f}%, {interval[1] * 100:.1f}%]" if interval else "—",
        )

    def _render_positions(self, positions, *, known: bool = True) -> None:
        if not known:
            self._positions_empty.set(
                "?", t("risk.positions.unknown"), t("risk.positions.unknown.detail")
            )
            self._positions_empty.setVisible(True)
            self._table.setVisible(False)
            self._table.setRowCount(0)
            return
        self._positions_empty.set(
            "○", t("risk.no_positions"), t("risk.no_positions.detail")
        )
        self._positions_empty.setVisible(not positions)
        self._table.setVisible(bool(positions))
        self._table.setRowCount(len(positions))

        for row, position in enumerate(positions):
            long = position.direction.value > 0
            bounded = position.stop_loss > 0
            cells = [
                (position.symbol, None, True, False),
                (
                    t("dir.long") if long else t("dir.short"),
                    PALETTE.long if long else PALETTE.short,
                    False,
                    False,
                ),
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
                    t("cell.bounded") if bounded else t("cell.unbounded"),
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
