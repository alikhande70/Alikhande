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

from ...core.enums import ExecState, RunMode
from ..components import Card, EmptyState, KeyValue, StatusChip, label, rule
from ..theme import PALETTE, SPACE, TYPE

# The happy path, in order. UNKNOWN is deliberately not on it: it is not a later
# stage of progress, it is the absence of progress, and drawing it as a step
# would suggest the order is further along than anybody knows.
PIPELINE = [
    (ExecState.SUBMITTING, "Submitting"),
    (ExecState.ACCEPTED, "Accepted"),
    (ExecState.PARTIALLY_FILLED, "Partial"),
    (ExecState.FILLED, "Filled"),
    (ExecState.POSITION_ACTIVE, "Position"),
    (ExecState.COMPLETED, "Completed"),
]

ORDER_HEADERS = ["Ticket", "Symbol", "State", "Initial", "Current", "Price"]


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
        self._review = Card("Manual review required")
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
        self._note.setPlaceholderText(
            "State what you verified in MetaTrader — e.g. 'checked Trade and History "
            "tabs, no order or position under magic 20260806'"
        )
        self._acknowledge = QPushButton("Acknowledge and clear")
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
        self._pipeline_card = Card("Current execution")
        self._pipeline_row = QHBoxLayout()
        self._pipeline_row.setSpacing(SPACE.sm)
        self._steps: list[StatusChip] = []
        for _, name in PIPELINE:
            chip = StatusChip("○", name.upper(), "neutral")
            self._steps.append(chip)
            self._pipeline_row.addWidget(chip)
        self._pipeline_row.addStretch(1)
        self._pipeline_card.add_layout(self._pipeline_row)
        self._pipeline_card.add(rule())

        self._detail = KeyValue(150)
        for key in (
            "Execution id",
            "Symbol",
            "State",
            "Resolved",
            "Order ticket",
            "Deal ticket",
            "Position id",
            "Requested / filled",
            "Retcode",
            "Message",
        ):
            self._detail.row(key)
        self._pipeline_card.add(self._detail)

        self._idle = EmptyState(
            "○",
            "No execution in flight",
            "Nothing has been submitted in this session. When an order is sent its "
            "progress appears here, and if the broker cannot account for it the "
            "submit gate closes until you clear it.",
        )
        self._pipeline_card.add(self._idle)
        root.addWidget(self._pipeline_card)

        # ---- policy ----------------------------------------------------------
        policy = Card("Execution policy")
        grid = QHBoxLayout()
        grid.setSpacing(SPACE.xl)

        left = KeyValue(150)
        for key in ("Run mode", "Account type", "Real accounts", "Order boundary"):
            left.row(key)
        left.stretch()
        grid.addWidget(left, 1)

        right = KeyValue(150)
        for key in ("Arming", "Arm TTL", "Reconcile grace", "Magic number"):
            right.row(key)
        right.stretch()
        grid.addWidget(right, 1)

        self._policy_left, self._policy_right = left, right
        policy.add_layout(grid)
        root.addWidget(policy)

        # ---- working orders --------------------------------------------------
        orders = Card("Working orders")
        self._table = QTableWidget(0, len(ORDER_HEADERS))
        self._table.setHorizontalHeaderLabels(ORDER_HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(38)
        self._table.horizontalHeader().setStretchLastSection(True)
        orders.add(self._table, 1)
        self._orders_empty = EmptyState("○", "No working orders", "")
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
                f"Execution {execution.execution_id} on {execution.symbol} could not be "
                "resolved against open positions, working orders, order history or deal "
                f"history after {config.execution.reconcile_grace_seconds}s.\n\n"
                "An order may be live that this application cannot see, so submission is "
                "blocked — and stays blocked across a restart. Verify the account in "
                "MetaTrader before clearing this."
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

        for index, (chip, (_, name)) in enumerate(zip(self._steps, PIPELINE)):
            if unknown:
                chip.set("?", name.upper(), "unknown")
            elif index < reached:
                chip.set("✓", name.upper(), "good")
            elif index == reached:
                chip.set("●", name.upper(), "warning" if not execution.terminal else "good")
            else:
                chip.set("○", name.upper(), "neutral")

    def _render_detail(self, execution) -> None:
        self._detail.set("Execution id", execution.execution_id or "—")
        self._detail.set("Symbol", execution.symbol or "—")
        self._detail.set(
            "State",
            execution.state.name,
            PALETTE.critical
            if execution.state == ExecState.UNKNOWN
            else (PALETTE.good if execution.terminal else PALETTE.warning),
        )
        self._detail.set(
            "Resolved",
            "yes" if execution.terminal else "NO — gate held shut",
            PALETTE.good if execution.terminal else PALETTE.warning,
        )
        self._detail.set("Order ticket", str(execution.order_ticket or "—"))
        self._detail.set("Deal ticket", str(execution.deal_ticket or "—"))
        self._detail.set("Position id", str(execution.position_id or "—"))
        self._detail.set(
            "Requested / filled",
            f"{execution.requested_volume:.2f} / {execution.filled_volume:.2f}",
        )
        self._detail.set("Retcode", str(execution.retcode or "—"))
        self._detail.set("Message", execution.message or "—")

    def _render_policy(self, snapshot) -> None:
        config = self._config
        account = snapshot.account

        self._policy_left.set("Run mode", snapshot.mode.name.replace("_", " "))
        if account is None:
            self._policy_left.set("Account type", "no account", PALETTE.ink_muted)
        else:
            self._policy_left.set(
                "Account type",
                "DEMO" if account.is_demo else "NOT DEMO",
                PALETTE.good if account.is_demo else PALETTE.critical,
            )
        self._policy_left.set("Real accounts", "blocked unconditionally", PALETTE.good)
        self._policy_left.set("Order boundary", "core.execution only", PALETTE.ink_secondary)

        self._policy_right.set(
            "Arming",
            "arm + confirm required"
            if snapshot.mode == RunMode.DEMO_CONFIRM
            else "not applicable in this mode",
        )
        self._policy_right.set("Arm TTL", f"{config.execution.arm_ttl_seconds}s")
        self._policy_right.set(
            "Reconcile grace", f"{config.execution.reconcile_grace_seconds}s"
        )
        self._policy_right.set("Magic number", str(config.execution.magic))
