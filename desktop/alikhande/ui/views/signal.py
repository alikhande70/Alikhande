"""Signal view — one symbol, with the evidence shown rather than asserted.

Three things this earns over the v1 Detail tab:

**The chart.** v1 said "price is inside a demand zone" and gave the operator no
way to check. Here the zones are drawn, the candles are drawn, and the entry,
stop and target sit on the same price scale. Disagreeing with the system is now
possible, which is the only way trusting it can mean anything.

**The score as bars.** A two-column table of contributions makes the reader do
the comparison. Bars on a shared scale do it for them, and the dominant
contributor is visible without reading a single number.

**Gates as chips.** Each gate is an icon, a word and a colour, in that order of
importance, so a blocked signal announces *which* gate blocked it rather than
burying it in a semicolon-joined string.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...i18n import code as t_code
from ...i18n import fmt_count, fmt_money, fmt_percent, fmt_price, t
from ...core.enums import (
    REGIME_NAMES,
    SETUP_NAMES,
    Direction,
    NewsState,
    RunMode,
    SpreadState,
)
from ..charts import PriceChart, TradeLevels
from ..components import (
    BarBreakdown,
    Card,
    DirectionBadge,
    KeyValue,
    ScoreRing,
    StatusChip,
    label,
)
from ..theme import PALETTE, SPACE


class SignalView(QWidget):
    arm_requested = Signal(str)
    confirm_requested = Signal(str)

    def __init__(self, config, statistics):
        super().__init__()
        self._config = config
        self._statistics = statistics
        self._symbol = ""
        self._syncing = False

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

        # ---- header ----------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(SPACE.md)
        self._picker = QComboBox()
        self._picker.setMinimumWidth(190)
        self._picker.currentTextChanged.connect(self._on_pick)
        self._badge = DirectionBadge()
        self._setup = label("", "H3")
        self._regime = label("", "Caption")
        header.addWidget(self._picker)
        header.addWidget(self._badge)
        header.addWidget(self._setup)
        header.addWidget(self._regime)
        header.addStretch(1)

        self._chip_news = StatusChip("?", "NEWS", "unknown")
        self._chip_spread = StatusChip("○", "SPREAD", "neutral")
        self._chip_data = StatusChip("○", "DATA", "neutral")
        for chip in (self._chip_data, self._chip_spread, self._chip_news):
            header.addWidget(chip)
        root.addLayout(header)

        # ---- chart -----------------------------------------------------------
        chart_card = Card(t("signal.chart"))
        self._chart = PriceChart()
        chart_card.add(self._chart, 1)
        root.addWidget(chart_card)

        # ---- three columns ---------------------------------------------------
        columns = QHBoxLayout()
        columns.setSpacing(SPACE.md)

        score_card = Card(t("signal.why"))
        score_row = QHBoxLayout()
        score_row.setSpacing(SPACE.lg)
        self._ring = ScoreRing(config.scoring.score_threshold, 92)
        score_row.addWidget(self._ring, 0, Qt.AlignmentFlag.AlignTop)
        self._breakdown = BarBreakdown()
        score_row.addWidget(self._breakdown, 1)
        score_card.add_layout(score_row)
        self._score_note = label("", "Caption")
        self._score_note.setWordWrap(True)
        score_card.add(self._score_note)
        columns.addWidget(score_card, 3)

        plan_card = Card(t("signal.plan"))
        self._plan = KeyValue(112)
        self._plan_keys = [
            "plan.entry", "plan.stop", "plan.target", "plan.rr",
            "plan.lots", "plan.risk", "plan.margin", "plan.expires",
            "plan.historical",
        ]
        for key in self._plan_keys:
            self._plan.row(t(key))
        self._plan.stretch()
        plan_card.add(self._plan)
        columns.addWidget(plan_card, 2)

        root.addLayout(columns)

        # ---- refusals --------------------------------------------------------
        self._refusal_card = Card(t("signal.refusals"))
        self._refusals = QVBoxLayout()
        self._refusals.setSpacing(SPACE.sm)
        self._refusal_card.add_layout(self._refusals)
        self._refusal_chips: list[StatusChip] = []
        root.addWidget(self._refusal_card)

        # ---- execute ---------------------------------------------------------
        execute = Card(t("signal.execute"))
        row = QHBoxLayout()
        row.setSpacing(SPACE.md)

        self._arm = QPushButton(t("btn.arm"))
        self._arm.setObjectName("Arm")
        self._arm.setMinimumWidth(130)
        self._arm.clicked.connect(lambda: self.arm_requested.emit(self._symbol))

        self._countdown = QProgressBar()
        self._countdown.setTextVisible(False)
        self._countdown.setFixedWidth(150)
        self._countdown.setFixedHeight(8)
        self._countdown.setStyleSheet(
            f"QProgressBar {{ background: {PALETTE.grid}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {PALETTE.warning}; border-radius: 4px; }}"
        )

        self._confirm = QPushButton(t("btn.confirm"))
        self._confirm.setObjectName("Confirm")
        self._confirm.setMinimumWidth(180)
        self._confirm.clicked.connect(lambda: self.confirm_requested.emit(self._symbol))

        self._status = label("", "Body")
        self._status.setWordWrap(True)

        row.addWidget(self._arm)
        row.addWidget(self._countdown)
        row.addWidget(self._confirm)
        row.addWidget(self._status, 1)
        execute.add_layout(row)
        root.addWidget(execute)
        root.addStretch(1)

        self._arm.setEnabled(False)
        self._confirm.setEnabled(False)

    # ------------------------------------------------------------------ state
    def _on_pick(self, symbol: str) -> None:
        if not self._syncing and symbol:
            self._symbol = symbol

    def select(self, symbol: str) -> None:
        index = self._picker.findText(symbol)
        if index >= 0:
            self._picker.setCurrentIndex(index)
            self._symbol = symbol

    # ----------------------------------------------------------------- render
    def update_view(self, snapshot) -> None:
        views = [v for v in snapshot.symbols if v.resolved]
        names = [v.symbol for v in views]
        existing = [self._picker.itemText(i) for i in range(self._picker.count())]

        if names and existing != names:
            self._syncing = True
            current = self._symbol
            self._picker.clear()
            self._picker.addItems(names)
            self._syncing = False
            if current in names:
                self._picker.setCurrentText(current)
            else:
                self._symbol = names[0]
                self._picker.setCurrentIndex(0)

        view = next((v for v in views if v.symbol == self._symbol), None)
        if view is None:
            self._arm.setEnabled(False)
            self._confirm.setEnabled(False)
            return

        digits = view.spec.digits if view.spec else 5
        signal = view.signal
        plan = view.plan

        # ---- header ---------------------------------------------------------
        self._badge.set(int(signal.direction) if signal else 0)
        self._setup.setText(SETUP_NAMES[signal.setup] if signal else t("signal.no_setup"))
        self._regime.setText(
            f"{REGIME_NAMES[signal.regime]} · {view.regime_reason}" if signal else ""
        )

        spread_state = view.snapshot.spread_state
        self._chip_spread.set(
            "✓" if spread_state == SpreadState.NORMAL else "!",
            f"{spread_state.name}  {view.snapshot.spread_points:.1f}pts",
            "good"
            if spread_state == SpreadState.NORMAL
            else ("unknown" if spread_state == SpreadState.WARMING_UP else "warning"),
        )
        self._chip_data.set("✓", view.snapshot.data_state.name, "good"
                            if view.snapshot.data_state.name == "READY" else "warning")
        news_map = {
            NewsState.CLEAR: ("✓", "good"),
            NewsState.BLOCKED: ("✕", "critical"),
            NewsState.UNKNOWN: ("?", "unknown"),
        }
        icon, tone = news_map[view.news.state]
        self._chip_news.set(icon, f"NEWS {view.news.state.name}", tone)
        self._chip_news.setToolTip(view.news.reason or "")

        # ---- chart ----------------------------------------------------------
        levels = TradeLevels()
        if signal is not None and signal.direction != Direction.NONE:
            levels = TradeLevels(
                entry=signal.preferred_entry,
                stop=signal.stop_loss,
                target=signal.take_profit,
                direction=int(signal.direction),
            )
        self._chart.set(
            view.bars, view.zones, levels, digits, t("signal.chart.title", symbol=view.symbol)
        )

        # ---- score ----------------------------------------------------------
        if signal is None:
            self._ring.set(0.0, t("common.none"))
            self._breakdown.set([])
            self._score_note.setText("")
        else:
            winning = max(signal.long_score, signal.short_score)
            self._ring.set(winning, t("col.score").lower())
            components = signal.components or (
                signal.long_components
                if signal.long_score >= signal.short_score
                else signal.short_components
            )
            self._breakdown.set(
                [(c.component.replace("_", " ").title(), c.contribution) for c in components]
            )
            self._score_note.setText(
                t(
                    "signal.score_note",
                    long=fmt_count(int(signal.long_score)),
                    short=fmt_count(int(signal.short_score)),
                    threshold=fmt_count(int(self._config.scoring.score_threshold)),
                    separation=fmt_count(int(self._config.scoring.score_separation)),
                )
            )

        # ---- plan -----------------------------------------------------------
        def price(value: float) -> str:
            return fmt_price(value, digits) if value and value > 0 else t("common.none")

        if signal is not None:
            self._plan.set(t("plan.entry"), price(signal.preferred_entry))
            self._plan.set(t("plan.stop"), price(signal.stop_loss), PALETTE.critical)
            self._plan.set(t("plan.target"), price(signal.take_profit), PALETTE.good)
            self._plan.set(
                t("plan.historical"),
                self._statistics.format_probability(signal),
                PALETTE.ink if signal.has_historical_estimate else PALETTE.ink_muted,
            )
        else:
            for key in ("plan.entry", "plan.stop", "plan.target", "plan.historical"):
                self._plan.set(t(key), t("common.none"), PALETTE.ink_faint)

        if plan is not None and plan.valid:
            risk_distance = abs(plan.entry - plan.stop_loss)
            reward = abs(plan.take_profit - plan.entry)
            self._plan.set(
                t("plan.rr"),
                f"1 : {reward / risk_distance:.2f}" if risk_distance > 0 else t("common.none"),
            )
            self._plan.set(t("plan.lots"), f"{plan.lot_size:.2f}")
            self._plan.set(
                t("plan.risk"),
                f"{fmt_money(plan.actual_risk_amount)} ({fmt_percent(plan.risk_percent)})",
            )
            self._plan.set(t("plan.margin"), fmt_money(plan.margin_required))
            remaining = max(0, plan.expires_at - snapshot.now)
            self._plan.set(
                t("plan.expires"),
                fmt_count(remaining),
                PALETTE.warning if remaining < 10 else None,
            )
        else:
            for key in ("plan.rr", "plan.lots", "plan.risk", "plan.margin", "plan.expires"):
                self._plan.set(t(key), t("common.none"), PALETTE.ink_faint)

        # ---- refusals -------------------------------------------------------
        self._render_refusals(view, snapshot)

        # ---- execute --------------------------------------------------------
        self._render_execute(view, snapshot)

    def _render_refusals(self, view, snapshot) -> None:
        reasons: list[tuple[str, str]] = []
        signal, plan = view.signal, view.plan

        if signal is not None:
            for code in signal.validation_codes:
                reasons.append((code, "critical" if signal.hard_blocked else "warning"))
        if plan is not None and not plan.valid:
            for code in plan.validation_codes:
                reasons.append((code, "warning"))
        if view.news_blocks:
            reasons.append((f"NEWS_{view.news.state.name}", "critical"))
        if not snapshot.may_trade:
            reasons.extend((code, "critical") for code in snapshot.guard_codes)

        self._refusal_card.setVisible(bool(reasons))
        while len(self._refusal_chips) < len(reasons):
            chip = StatusChip("✕", "", "critical")
            self._refusal_chips.append(chip)
            self._refusals.addWidget(chip, 0, Qt.AlignmentFlag.AlignLeft)

        for index, chip in enumerate(self._refusal_chips):
            if index < len(reasons):
                code, tone = reasons[index]
                chip.set(
                    "✕" if tone == "critical" else "!",
                    t_code(code),
                    tone,
                )
                chip.setVisible(True)
            else:
                chip.setVisible(False)

    def _render_execute(self, view, snapshot) -> None:
        armed_here = snapshot.armed_symbol == view.symbol
        has_plan = view.plan is not None and view.plan.valid
        confirmable = snapshot.mode in (RunMode.SHADOW, RunMode.DEMO_CONFIRM)
        gated = view.news_blocks or not snapshot.may_trade or snapshot.requires_manual_review

        self._arm.setEnabled(confirmable and has_plan and not armed_here and not gated)
        self._confirm.setEnabled(confirmable and has_plan and armed_here and not gated)

        if armed_here:
            ttl = max(1, self._config.execution.arm_ttl_seconds)
            self._countdown.setMaximum(ttl)
            self._countdown.setValue(snapshot.armed_seconds)
            self._set_status(
                t("exec.armed", seconds=fmt_count(snapshot.armed_seconds)),
                PALETTE.warning,
            )
            return

        self._countdown.setValue(0)
        if not confirmable:
            self._set_status(
                t(
                    "exec.mode_blocks",
                    mode={
                        RunMode.ALERT_ONLY: t("mode.alert"),
                        RunMode.SHADOW: t("mode.shadow"),
                        RunMode.DEMO_CONFIRM: t("mode.demo"),
                    }.get(snapshot.mode, snapshot.mode.name),
                ),
                PALETTE.ink_muted,
            )
        elif snapshot.requires_manual_review:
            self._set_status(t("exec.review_blocks"), PALETTE.critical)
        elif view.news_blocks:
            self._set_status(t("exec.news_blocks"), PALETTE.critical)
        elif not snapshot.may_trade:
            self._set_status("; ".join(snapshot.guard_codes), PALETTE.critical)
        elif has_plan:
            self._set_status(t("exec.ready"), PALETTE.ink_secondary)
        else:
            self._set_status(t("exec.no_plan"), PALETTE.ink_muted)

    def _set_status(self, text: str, colour: str) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {colour};")
