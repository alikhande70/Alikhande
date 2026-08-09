"""Risk tab — exposure, guards and the evidence base.

Two things live here that the MQL5 panel could not show, both because the data
did not exist: the outcome record, and the unbounded-position warning.

The outcome panel is deliberately blunt about an empty database. "No outcomes
recorded yet" is the correct and complete answer until trades resolve, and
dressing it up as 0% would be a fabricated statistic.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...core.statistics import wilson
from ..theme import PALETTE
from ..widgets import Card, KeyValue, Metric, Table


class RiskTab(QWidget):
    def __init__(self, config, repositories=None) -> None:
        super().__init__()
        self._config = config
        self._repo = repositories

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(PALETTE.gap)

        strip = QHBoxLayout()
        strip.setSpacing(PALETTE.gap)
        self._m_open = Metric("Open risk", "0.00%", f"cap {config.risk.max_open_risk_pct:.2f}%")
        self._m_positions = Metric("Positions", "0", "opened by this app")
        self._m_equity = Metric("Equity", "—", "account currency")
        self._m_drawdown = Metric("Drawdown", "0.00%", "from peak equity")
        for metric in (self._m_open, self._m_positions, self._m_equity, self._m_drawdown):
            strip.addWidget(metric)
        root.addLayout(strip)

        columns = QHBoxLayout()
        columns.setSpacing(PALETTE.gap)

        policy_card = Card("Risk policy")
        self._policy = KeyValue()
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
        policy_card.add(self._policy)
        columns.addWidget(policy_card, 1)

        guard_card = Card("Guard state")
        self._guards = KeyValue()
        for key in (
            "Trading permitted",
            "Breached guards",
            "Peak equity",
            "Day-start equity",
            "Consecutive losses",
            "Daily risk used",
            "Unbounded positions",
        ):
            self._guards.row(key)
        self._guards.stretch()
        guard_card.add(self._guards)
        columns.addWidget(guard_card, 1)

        outcome_card = Card("Evidence base")
        self._outcomes = KeyValue()
        for key in (
            "Resolved trades",
            "Wins / losses",
            "Win rate",
            "95% Wilson",
            "Total R",
            "Expectancy",
            "Sample policy",
        ):
            self._outcomes.row(key)
        self._outcomes.stretch()
        outcome_card.add(self._outcomes)
        columns.addWidget(outcome_card, 1)

        root.addLayout(columns)

        table_card = Card("Open positions")
        self._table = Table(
            ["Symbol", "Side", "Volume", "Entry", "Stop", "Target", "Profit", "Risk"]
        )
        table_card.add(self._table, 1)
        root.addWidget(table_card, 1)

        self._render_policy()

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
            PALETTE.ok if risk.guards_enabled else PALETTE.text_faint,
        )

    def update_view(self, snapshot, positions, exposure, guard_state) -> None:
        account = snapshot.account
        equity = account.equity if account else 0.0

        self._m_open.set(
            f"{exposure.open_risk_pct:.2f}%",
            f"cap {self._config.risk.max_open_risk_pct:.2f}%",
            PALETTE.danger
            if exposure.open_risk_pct > self._config.risk.max_open_risk_pct
            else None,
        )
        self._m_positions.set(str(exposure.open_positions), "opened by this app")
        self._m_equity.set(
            f"{equity:,.2f}" if account else "—",
            account.currency if account else "no account",
        )

        drawdown = 0.0
        if guard_state.peak_equity > 0 and equity > 0:
            drawdown = (guard_state.peak_equity - equity) / guard_state.peak_equity * 100.0
        self._m_drawdown.set(
            f"{drawdown:.2f}%",
            "from peak equity",
            PALETTE.danger if drawdown >= self._config.risk.total_drawdown_limit_pct else None,
        )

        self._guards.set(
            "Trading permitted",
            "yes" if snapshot.may_trade else "NO",
            PALETTE.ok if snapshot.may_trade else PALETTE.danger,
        )
        self._guards.set(
            "Breached guards",
            "; ".join(snapshot.guard_codes) if snapshot.guard_codes else "none",
            PALETTE.danger if snapshot.guard_codes else PALETTE.text_dim,
        )
        self._guards.set("Peak equity", f"{guard_state.peak_equity:,.2f}")
        self._guards.set("Day-start equity", f"{guard_state.day_start_equity:,.2f}")
        self._guards.set("Consecutive losses", str(guard_state.consecutive_losses))
        self._guards.set("Daily risk used", f"{guard_state.daily_risk_used_pct:.2f}%")

        # An unbounded position is not a zero-risk position. While any exist,
        # every percentage on this tab is a lower bound and no new risk is
        # admitted — so it is stated in those words rather than as a count.
        if exposure.unbounded_positions:
            self._guards.set(
                "Unbounded positions",
                f"{exposure.unbounded_positions} — caps are lower bounds, "
                f"new risk refused ({', '.join(exposure.unbounded_symbols)})",
                PALETTE.danger,
            )
        else:
            self._guards.set("Unbounded positions", "none", PALETTE.text_dim)

        self._render_outcomes()

        self._table.clear_rows()
        self._table.setRowCount(len(positions))
        for row, position in enumerate(positions):
            self._table.set_cell(row, 0, position.symbol, mono=True)
            side = "LONG" if position.direction.value > 0 else "SHORT"
            self._table.set_cell(
                row, 1, side, PALETTE.long if side == "LONG" else PALETTE.short
            )
            self._table.set_cell(row, 2, f"{position.volume:.2f}", mono=True, align_right=True)
            self._table.set_cell(row, 3, f"{position.price_open:.5f}", mono=True, align_right=True)
            self._table.set_cell(
                row,
                4,
                f"{position.stop_loss:.5f}" if position.stop_loss > 0 else "NONE",
                PALETTE.danger if position.stop_loss <= 0 else None,
                mono=True,
                align_right=True,
            )
            self._table.set_cell(
                row,
                5,
                f"{position.take_profit:.5f}" if position.take_profit > 0 else "—",
                mono=True,
                align_right=True,
            )
            self._table.set_cell(
                row,
                6,
                f"{position.profit:+.2f}",
                PALETTE.ok if position.profit >= 0 else PALETTE.danger,
                mono=True,
                align_right=True,
            )
            self._table.set_cell(
                row,
                7,
                "unbounded" if position.stop_loss <= 0 else "bounded",
                PALETTE.danger if position.stop_loss <= 0 else PALETTE.text_dim,
            )
        self._table.fit_columns()

    def _render_outcomes(self) -> None:
        floor = self._config.statistics.min_outcome_sample
        self._outcomes.set("Sample policy", f"{floor} trades minimum  [POLICY]")

        if self._repo is None or not self._repo.ready:
            for key in (
                "Resolved trades",
                "Wins / losses",
                "Win rate",
                "95% Wilson",
                "Total R",
                "Expectancy",
            ):
                self._outcomes.set(key, "no database", PALETTE.muted)
            return

        summary = self._repo.outcome_summary()
        total = int(summary["total"])

        self._outcomes.set("Resolved trades", str(total))
        if total == 0:
            for key in ("Wins / losses", "Win rate", "95% Wilson", "Total R", "Expectancy"):
                self._outcomes.set(key, "no outcomes recorded yet", PALETTE.muted)
            return

        wins = int(summary["wins"])
        self._outcomes.set("Wins / losses", f"{wins} / {total - wins}")
        self._outcomes.set("Total R", f"{summary['sum_r']:+.2f}")
        self._outcomes.set("Expectancy", f"{summary['avg_r']:+.3f} R")

        if total < floor:
            self._outcomes.set(
                "Win rate",
                f"withheld — {total}/{floor} samples",
                PALETTE.muted,
            )
            self._outcomes.set("95% Wilson", "—", PALETTE.muted)
            return

        interval = wilson(wins, total)
        self._outcomes.set("Win rate", f"{wins / total * 100:.1f}%")
        self._outcomes.set(
            "95% Wilson",
            f"[{interval[0] * 100:.1f}%, {interval[1] * 100:.1f}%]" if interval else "—",
        )
