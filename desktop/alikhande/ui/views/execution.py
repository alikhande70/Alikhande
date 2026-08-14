"""Execution view — the in-flight order, and the manual-review escape hatch.

The most important thing here is the one that should almost never appear: when
an execution cannot be reconciled against the broker, this is where the operator
sees why, and the only place they can clear it.

Clearing it is deliberately awkward. It requires typing a note of real length,
because the alternative — a bare "OK" button — turns a decision that means *"I
have checked the account myself and there is no untracked order"* into a reflex.

The state machine is drawn as a progression rather than printed as a word, so
"where is this order" is answerable at a glance and the difference between
"finished" and "we do not know" is visible rather than read.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...i18n import fmt_count, fmt_money, fmt_percent, fmt_price, t
from ...core.enums import ExecState, RunMode
from ..components import Card, EmptyState, KeyValue, StatusChip, label, rule
from ..theme import PALETTE, SPACE, TYPE

# The happy path, in order. UNKNOWN is deliberately not on it: it is not a later
# stage of progress, it is the absence of progress, and drawing it as a step
# would suggest the order is further along than anybody knows.
PIPELINE = [
    (ExecState.SUBMITTING, "step.submitting"),
    (ExecState.ACCEPTED, "step.accepted"),
    (ExecState.PARTIALLY_FILLED, "step.partial"),
    (ExecState.FILLED, "step.filled"),
    (ExecState.POSITION_ACTIVE, "step.position"),
    (ExecState.COMPLETED, "step.completed"),
]

ORDER_KEYS = ["col.symbol", "col.symbol", "col.state", "col.volume", "col.volume", "col.entry"]


class ExecutionView(QWidget):
    acknowledge_requested = Signal(str)

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

        # ---- manual review ---------------------------------------------------
        self._review = Card(t("exec.review_title"))
        self._review.setStyleSheet(
            f"QFrame#Card {{ background: {PALETTE.critical_wash};"
            f" border: 1px solid {PALETTE.critical}; border-radius: 10px; }}"
        )
        self._review_text = label("", "Body")
        self._review_text.setWordWrap(True)
        self._review_text.setStyleSheet(f"color: {PALETTE.critical};")
        self._review.add(self._review_text)

        review_row = QHBoxLayout()
        review_row.setSpacing(SPACE.md)
        self._note = QLineEdit()
        self._note.setPlaceholderText(t("exec.note_placeholder"))
        self._acknowledge = QPushButton(t("exec.acknowledge"))
        self._acknowledge.setObjectName("Confirm")
        self._acknowledge.setEnabled(False)
        self._acknowledge.clicked.connect(
            lambda: self.acknowledge_requested.emit(self._note.text())
        )
        self._note.textChanged.connect(
            lambda text: self._acknowledge.setEnabled(len(text.strip()) >= 15)
        )
        review_row.addWidget(self._note, 1)
        review_row.addWidget(self._acknowledge)
        self._review.add_layout(review_row)
        root.addWidget(self._review)
        self._review.setVisible(False)

        # ---- pipeline --------------------------------------------------------
        self._pipeline_card = Card(t("exec.current"))
        self._pipeline_row = QHBoxLayout()
        self._pipeline_row.setSpacing(SPACE.sm)
        self._steps: list[StatusChip] = []
        for _, key in PIPELINE:
            chip = StatusChip("○", t(key).upper(), "neutral")
            self._steps.append(chip)
            self._pipeline_row.addWidget(chip)
        self._pipeline_row.addStretch(1)
        self._pipeline_card.add_layout(self._pipeline_row)
        self._pipeline_card.add(rule())

        self._detail = KeyValue(150)
        for key in (
            t("exec.field.id"),
            t("exec.field.symbol"),
            t("exec.field.state"),
            t("exec.field.resolved"),
            t("exec.field.order"),
            t("exec.field.deal"),
            t("exec.field.position"),
            t("exec.field.volume"),
            t("exec.field.retcode"),
            t("exec.field.message"),
        ):
            self._detail.row(key)
        self._pipeline_card.add(self._detail)

        self._idle = EmptyState("○", t("exec.idle"), t("exec.idle.detail"))
        self._pipeline_card.add(self._idle)
        root.addWidget(self._pipeline_card)

        # ---- policy ----------------------------------------------------------
        policy = Card(t("exec.policy"))
        grid = QHBoxLayout()
        grid.setSpacing(SPACE.xl)

        left = KeyValue(150)
        for key in (t("exec.field.mode"), t("exec.field.account"), t("exec.field.real"), t("exec.field.boundary")):
            left.row(key)
        left.stretch()
        grid.addWidget(left, 1)

        right = KeyValue(150)
        for key in (t("exec.field.arming"), t("exec.field.ttl"), t("exec.field.grace"), t("exec.field.magic")):
            right.row(key)
        right.stretch()
        grid.addWidget(right, 1)

        self._policy_left, self._policy_right = left, right
        policy.add_layout(grid)
        root.addWidget(policy)

        # ---- working orders --------------------------------------------------
        orders = Card(t("exec.orders"))
        self._table = QTableWidget(0, len(ORDER_KEYS))
        self._table.setHorizontalHeaderLabels([t(k) for k in ORDER_KEYS])
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(38)
        self._table.horizontalHeader().setStretchLastSection(True)
        orders.add(self._table, 1)
        self._orders_empty = EmptyState("○", t("exec.no_orders"), "")
        orders.add(self._orders_empty)
        root.addWidget(orders, 1)
        root.addStretch(1)

    # ----------------------------------------------------------------- render
    def update_view(self, snapshot, execution, orders) -> None:
        config = self._config
        in_flight = execution.execution_id != ""

        self._review.setVisible(snapshot.requires_manual_review)
        if snapshot.requires_manual_review:
            self._review_text.setText(
                t(
                    "exec.review_body",
                    id=execution.execution_id,
                    symbol=execution.symbol,
                    grace=fmt_count(config.execution.reconcile_grace_seconds),
                )
            )

        self._idle.setVisible(not in_flight)
        self._detail.setVisible(in_flight)
        for chip in self._steps:
            chip.setVisible(in_flight)

        if in_flight:
            self._render_pipeline(execution)
            self._render_detail(execution)

        self._render_policy(snapshot)

        self._orders_empty.setVisible(not orders)
        self._table.setVisible(bool(orders))
        self._table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            values = [
                str(order.ticket),
                order.symbol,
                order.state,
                f"{order.volume_initial:.2f}",
                f"{order.volume_current:.2f}",
                f"{order.price_open:.5f}",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column != 2:
                    from PySide6.QtGui import QFont

                    item.setFont(QFont(PALETTE.mono.split(",")[0].strip("'"), TYPE.small))
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)

    def _render_pipeline(self, execution) -> None:
        # UNKNOWN is not a stage. When it is the state, every step reads as
        # unreached and the detail block carries the explanation — the pipeline
        # must never imply progress nobody can verify.
        unknown = execution.state == ExecState.UNKNOWN
        reached = -1
        if not unknown:
            for index, (state, _) in enumerate(PIPELINE):
                if execution.state == state:
                    reached = index
                    break
            if execution.state == ExecState.RECONCILING:
                reached = 0

        for index, (chip, (_, key)) in enumerate(zip(self._steps, PIPELINE)):
            name = t(key).upper()
            if unknown:
                chip.set("?", name, "unknown")
            elif index < reached:
                chip.set("✓", name, "good")
            elif index == reached:
                chip.set("●", name, "warning" if not execution.terminal else "good")
            else:
                chip.set("○", name, "neutral")

    def _render_detail(self, execution) -> None:
        self._detail.set(t("exec.field.id"), execution.execution_id or "—")
        self._detail.set("Symbol", execution.symbol or "—")
        self._detail.set(
            "State",
            execution.state.name,
            PALETTE.critical
            if execution.state == ExecState.UNKNOWN
            else (PALETTE.good if execution.terminal else PALETTE.warning),
        )
        self._detail.set(
            t("exec.field.resolved"),
            t("exec.resolved.yes") if execution.terminal else t("exec.resolved.no"),
            PALETTE.good if execution.terminal else PALETTE.warning,
        )
        self._detail.set(t("exec.field.order"), str(execution.order_ticket or "—"))
        self._detail.set(t("exec.field.deal"), str(execution.deal_ticket or "—"))
        self._detail.set(t("exec.field.position"), str(execution.position_id or "—"))
        self._detail.set(
            t("exec.field.volume"),
            f"{execution.requested_volume:.2f} / {execution.filled_volume:.2f}",
        )
        self._detail.set(t("exec.field.retcode"), str(execution.retcode or "—"))
        self._detail.set(t("exec.field.message"), execution.message or "—")

    def _render_policy(self, snapshot) -> None:
        config = self._config
        account = snapshot.account

        self._policy_left.set(
            t("exec.field.mode"),
            {
                RunMode.ALERT_ONLY: t("mode.alert"),
                RunMode.SHADOW: t("mode.shadow"),
                RunMode.DEMO_CONFIRM: t("mode.demo"),
            }.get(snapshot.mode, snapshot.mode.name),
        )
        if account is None:
            self._policy_left.set(t("exec.field.account"), t("chip.no_account"), PALETTE.ink_muted)
        else:
            self._policy_left.set(
                t("exec.field.account"),
                t("chip.demo") if account.is_demo else t("chip.real_blocked"),
                PALETTE.good if account.is_demo else PALETTE.critical,
            )
        self._policy_left.set(t("exec.field.real"), t("exec.real_blocked"), PALETTE.good)
        self._policy_left.set(t("exec.field.boundary"), t("exec.boundary"), PALETTE.ink_secondary)

        self._policy_right.set(
            t("exec.field.arming"),
            t("exec.arming.required")
            if snapshot.mode == RunMode.DEMO_CONFIRM
            else t("exec.arming.na"),
        )
        self._policy_right.set(t("exec.field.ttl"), f"{config.execution.arm_ttl_seconds}s")
        self._policy_right.set(
            t("exec.field.grace"), f"{config.execution.reconcile_grace_seconds}s"
        )
        self._policy_right.set(t("exec.field.magic"), str(config.execution.magic))
