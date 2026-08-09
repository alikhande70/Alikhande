"""Detail tab — one symbol, in full, with the Arm and Confirm controls.

This is where the score is *explained*. A bare number invites the operator to
trust it; the component breakdown lets them disagree with it, which is the
entire reason the scoring engine records components rather than just a total.

The Arm and Confirm controls live here and nowhere else. They are deliberately
separate widgets with different colours and a countdown between them, because
the safety property is that no single action can send an order.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.enums import (
    DIRECTION_NAMES,
    REGIME_NAMES,
    SETUP_NAMES,
    Direction,
    NewsState,
    RunMode,
)
from ...core.statistics import Statistics
from ..theme import PALETTE
from ..widgets import Card, KeyValue, Table


class DetailTab(QWidget):
    arm_requested = Signal(str)
    confirm_requested = Signal(str)

    def __init__(self, statistics: Statistics) -> None:
        super().__init__()
        self._statistics = statistics
        self._symbol = ""
        self._selecting = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(PALETTE.gap)

        # ---- symbol picker ---------------------------------------------------
        picker = QHBoxLayout()
        picker.setSpacing(10)
        label = QLabel("Symbol")
        label.setObjectName("Caption")
        self._picker = QComboBox()
        self._picker.setMinimumWidth(190)
        self._picker.currentTextChanged.connect(self._on_pick)
        picker.addWidget(label)
        picker.addWidget(self._picker)
        picker.addStretch(1)
        root.addLayout(picker)

        # ---- three columns ---------------------------------------------------
        columns = QHBoxLayout()
        columns.setSpacing(PALETTE.gap)

        setup_card = Card("Setup")
        self._setup = KeyValue()
        for key in (
            "Direction",
            "Setup",
            "Regime",
            "Rule score",
            "Historical",
            "Demand zone",
            "Supply zone",
            "Signal state",
            "Signal id",
        ):
            self._setup.row(key)
        self._setup.stretch()
        setup_card.add(self._setup)
        columns.addWidget(setup_card, 1)

        levels_card = Card("Levels and sizing")
        self._levels = KeyValue()
        for key in (
            "Bid / Ask",
            "Entry",
            "Stop loss",
            "Take profit",
            "Risk / reward",
            "Lot size",
            "Risk amount",
            "Margin",
            "Plan expires",
        ):
            self._levels.row(key)
        self._levels.stretch()
        levels_card.add(self._levels)
        columns.addWidget(levels_card, 1)

        gates_card = Card("Gates")
        self._gates = KeyValue()
        for key in ("News", "Spread", "Data", "Structure built", "Refusals"):
            self._gates.row(key)
        self._gates.stretch()
        gates_card.add(self._gates)
        columns.addWidget(gates_card, 1)

        root.addLayout(columns, 0)

        # ---- score breakdown -------------------------------------------------
        breakdown = Card("Why this score")
        self._components = Table(["Component", "Contribution"])
        breakdown.add(self._components, 1)
        root.addWidget(breakdown, 1)

        # ---- arm / confirm ---------------------------------------------------
        execute = Card("Execute")
        row = QHBoxLayout()
        row.setSpacing(12)

        self._arm = QPushButton("ARM")
        self._arm.setObjectName("Arm")
        self._arm.setMinimumWidth(130)
        self._arm.clicked.connect(lambda: self.arm_requested.emit(self._symbol))

        self._confirm = QPushButton("CONFIRM SEND")
        self._confirm.setObjectName("Confirm")
        self._confirm.setMinimumWidth(170)
        self._confirm.clicked.connect(lambda: self.confirm_requested.emit(self._symbol))

        self._countdown = QProgressBar()
        self._countdown.setTextVisible(False)
        self._countdown.setMaximumWidth(190)

        self._status = QLabel("Alert-only mode — nothing can be sent.")
        self._status.setObjectName("Caption")
        self._status.setWordWrap(True)

        row.addWidget(self._arm)
        row.addWidget(self._countdown)
        row.addWidget(self._confirm)
        row.addWidget(self._status, 1)
        execute.body().addLayout(row)
        root.addWidget(execute)

        self._set_execute_enabled(False, False)

    # ------------------------------------------------------------------ state
    def _on_pick(self, symbol: str) -> None:
        if not self._selecting:
            self._symbol = symbol

    def select(self, symbol: str) -> None:
        index = self._picker.findText(symbol)
        if index >= 0:
            self._picker.setCurrentIndex(index)
            self._symbol = symbol

    def _set_execute_enabled(self, can_arm: bool, can_confirm: bool) -> None:
        self._arm.setEnabled(can_arm)
        self._confirm.setEnabled(can_confirm)

    def set_status(self, text: str, colour: str | None = None) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {colour};" if colour else "")

    # ----------------------------------------------------------------- render
    def update_view(self, snapshot) -> None:
        views = [v for v in snapshot.symbols if v.resolved]
        names = [v.symbol for v in views]

        if names and [self._picker.itemText(i) for i in range(self._picker.count())] != names:
            self._selecting = True
            current = self._symbol
            self._picker.clear()
            self._picker.addItems(names)
            self._selecting = False
            if current in names:
                self._picker.setCurrentText(current)
            else:
                self._symbol = names[0]
                self._picker.setCurrentIndex(0)

        view = next((v for v in views if v.symbol == self._symbol), None)
        if view is None:
            self._set_execute_enabled(False, False)
            return

        digits = view.spec.digits if view.spec else 5
        signal = view.signal
        plan = view.plan

        def price(value: float) -> str:
            return f"{value:.{digits}f}" if value and value > 0 else "—"

        # ---- setup -----------------------------------------------------------
        if signal is None:
            for key in (
                "Direction",
                "Setup",
                "Regime",
                "Rule score",
                "Historical",
                "Demand zone",
                "Supply zone",
                "Signal state",
                "Signal id",
            ):
                self._setup.set(key, "—", PALETTE.text_faint)
            self._components.clear_rows()
        else:
            colour = {
                Direction.LONG: PALETTE.long,
                Direction.SHORT: PALETTE.short,
            }.get(signal.direction, PALETTE.text_faint)
            self._setup.set("Direction", DIRECTION_NAMES[signal.direction], colour)
            self._setup.set("Setup", SETUP_NAMES[signal.setup])
            self._setup.set("Regime", REGIME_NAMES[signal.regime])
            self._setup.set(
                "Rule score",
                f"L {signal.long_score:.0f}   S {signal.short_score:.0f}",
            )
            self._setup.set(
                "Historical",
                self._statistics.format_probability(signal),
                PALETTE.text if signal.has_historical_estimate else PALETTE.muted,
            )
            self._setup.set("Demand zone", signal.demand_relation.name)
            self._setup.set("Supply zone", signal.supply_relation.name)
            self._setup.set("Signal state", signal.state.name)
            self._setup.set("Signal id", signal.signal_id or "—")

            components = signal.components
            self._components.clear_rows()
            self._components.setRowCount(len(components))
            for row, component in enumerate(components):
                self._components.set_cell(row, 0, component.component)
                self._components.set_cell(
                    row,
                    1,
                    f"{component.contribution:+.1f}",
                    PALETTE.long if component.contribution > 0 else PALETTE.short,
                    mono=True,
                    align_right=True,
                )
            self._components.fit_columns()

        # ---- levels ----------------------------------------------------------
        snap = view.snapshot
        self._levels.set("Bid / Ask", f"{price(snap.bid)} / {price(snap.ask)}")
        if signal is not None:
            self._levels.set("Entry", price(signal.preferred_entry))
            self._levels.set("Stop loss", price(signal.stop_loss))
            self._levels.set("Take profit", price(signal.take_profit))
        if plan is not None and plan.valid:
            risk_distance = abs(plan.entry - plan.stop_loss)
            reward = abs(plan.take_profit - plan.entry)
            self._levels.set(
                "Risk / reward",
                f"1 : {reward / risk_distance:.2f}" if risk_distance > 0 else "—",
            )
            self._levels.set("Lot size", f"{plan.lot_size:.2f}")
            self._levels.set(
                "Risk amount", f"{plan.actual_risk_amount:.2f} ({plan.risk_percent:.2f}%)"
            )
            self._levels.set("Margin", f"{plan.margin_required:.2f}")
            remaining = max(0, plan.expires_at - snapshot.now)
            self._levels.set(
                "Plan expires",
                f"{remaining}s",
                PALETTE.warning if remaining < 10 else None,
            )
        else:
            for key in ("Risk / reward", "Lot size", "Risk amount", "Margin", "Plan expires"):
                self._levels.set(key, "—", PALETTE.text_faint)

        # ---- gates -----------------------------------------------------------
        news_colour = {
            NewsState.CLEAR: PALETTE.ok,
            NewsState.BLOCKED: PALETTE.danger,
            NewsState.UNKNOWN: PALETTE.muted,
        }[view.news.state]
        self._gates.set(
            "News",
            f"{view.news.state.name} / {view.news.source.name}"
            + (f" — {view.news.reason}" if view.news.reason else ""),
            news_colour,
        )
        self._gates.set(
            "Spread",
            f"{snap.spread_points:.1f} pts  {snap.spread_state.name}"
            + (f"  x{snap.spread_ratio:.2f}" if snap.spread_ratio else ""),
        )
        self._gates.set("Data", snap.data_state.name)
        self._gates.set(
            "Structure built",
            f"{snapshot.now - view.structure_built_at}s ago"
            if view.structure_built_at
            else "not built",
        )
        refusals = list(signal.validation_codes) if signal else []
        if plan is not None and not plan.valid:
            refusals += plan.validation_codes
        self._gates.set(
            "Refusals",
            "; ".join(refusals) if refusals else "none",
            PALETTE.warning if refusals else PALETTE.text_dim,
        )

        # ---- arm / confirm ---------------------------------------------------
        armed_here = snapshot.armed_symbol == view.symbol
        has_plan = plan is not None and plan.valid
        demo_mode = snapshot.mode == RunMode.DEMO_CONFIRM
        gated = view.news_blocks or not snapshot.may_trade or snapshot.requires_manual_review

        self._set_execute_enabled(
            demo_mode and has_plan and not armed_here and not gated,
            demo_mode and has_plan and armed_here,
        )

        if armed_here:
            self._countdown.setMaximum(max(1, snapshot.armed_seconds or 1))
            self._countdown.setValue(snapshot.armed_seconds)
            self.set_status(
                f"ARMED — confirm within {snapshot.armed_seconds}s or it expires.",
                PALETTE.warning,
            )
        else:
            self._countdown.setValue(0)
            if not demo_mode:
                self.set_status(
                    f"{snapshot.mode.name} — no order can be sent in this mode.",
                    PALETTE.text_faint,
                )
            elif snapshot.requires_manual_review:
                self.set_status(
                    "An execution is unresolved. Submission is blocked until it is "
                    "acknowledged on the Execution tab.",
                    PALETTE.danger,
                )
            elif view.news_blocks:
                self.set_status("Blocked by the news gate.", PALETTE.danger)
            elif not snapshot.may_trade:
                self.set_status("; ".join(snapshot.guard_codes), PALETTE.danger)
            elif has_plan:
                self.set_status("Plan ready. Arm, then confirm.", PALETTE.text_dim)
            else:
                self.set_status("No valid plan for this symbol.", PALETTE.text_faint)
