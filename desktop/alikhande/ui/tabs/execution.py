"""Execution tab — the in-flight order, and the manual-review escape hatch.

The most important thing on this tab is the one that should almost never
appear: when an execution cannot be reconciled against the broker, this is
where the operator sees why, and the only place they can clear it.

That clearing is deliberately awkward. It requires typing a note, because the
alternative — a bare "OK" button — turns a decision that means *"I have checked
the account myself and there is no untracked order"* into a reflex.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.enums import RunMode
from ..theme import PALETTE
from ..widgets import Card, KeyValue, Table


class ExecutionTab(QWidget):
    acknowledge_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(PALETTE.gap)

        # ---- manual review ---------------------------------------------------
        self._review = Card("Manual review required")
        self._review_text = QLabel()
        self._review_text.setWordWrap(True)
        self._review_text.setStyleSheet(f"color: {PALETTE.danger};")
        self._review.add(self._review_text)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._note = QLineEdit()
        self._note.setPlaceholderText(
            "Describe what you verified in the terminal, e.g. "
            "'checked Trade and History tabs — no order or position for this magic'"
        )
        self._acknowledge = QPushButton("Acknowledge and clear")
        self._acknowledge.setObjectName("Confirm")
        self._acknowledge.clicked.connect(
            lambda: self.acknowledge_requested.emit(self._note.text())
        )
        self._note.textChanged.connect(
            lambda text: self._acknowledge.setEnabled(len(text.strip()) >= 10)
        )
        self._acknowledge.setEnabled(False)
        row.addWidget(self._note, 1)
        row.addWidget(self._acknowledge)
        self._review.body().addLayout(row)
        root.addWidget(self._review)
        self._review.setVisible(False)

        # ---- current execution ------------------------------------------------
        columns = QHBoxLayout()
        columns.setSpacing(PALETTE.gap)

        current = Card("Current execution")
        self._current = KeyValue()
        for key in (
            "Execution id",
            "Symbol",
            "State",
            "Terminal",
            "Order ticket",
            "Deal ticket",
            "Position id",
            "Requested / filled",
            "Retcode",
            "Message",
            "Created",
            "Updated",
        ):
            self._current.row(key)
        self._current.stretch()
        current.add(self._current)
        columns.addWidget(current, 1)

        policy = Card("Execution policy")
        self._policy = KeyValue()
        for key in (
            "Run mode",
            "Account type",
            "Real accounts",
            "Order boundary",
            "Arming",
            "Arm TTL",
            "Reconcile grace",
            "Magic number",
        ):
            self._policy.row(key)
        self._policy.stretch()
        policy.add(self._policy)
        columns.addWidget(policy, 1)

        root.addLayout(columns)

        history = Card("Working orders")
        self._orders = Table(["Ticket", "Symbol", "State", "Initial", "Current", "Price"])
        history.add(self._orders, 1)
        root.addWidget(history, 1)

    def update_view(self, snapshot, execution, orders, config) -> None:
        self._review.setVisible(snapshot.requires_manual_review)
        if snapshot.requires_manual_review:
            self._review_text.setText(
                f"Execution {execution.execution_id} on {execution.symbol} could not be "
                f"resolved against open positions, working orders, order history or deal "
                f"history after {config.execution.reconcile_grace_seconds}s.\n\n"
                "An order may be live that this application cannot see, so submission is "
                "blocked — and stays blocked across a restart. Verify the account in "
                "MetaTrader before clearing this."
            )

        self._current.set("Execution id", execution.execution_id or "—")
        self._current.set("Symbol", execution.symbol or "—")
        self._current.set(
            "State",
            execution.state.name,
            PALETTE.danger
            if execution.state.name == "UNKNOWN"
            else (PALETTE.ok if execution.terminal else PALETTE.warning),
        )
        self._current.set(
            "Terminal",
            "yes (resolved)" if execution.terminal else "no",
            PALETTE.ok if execution.terminal else PALETTE.warning,
        )
        self._current.set("Order ticket", str(execution.order_ticket or "—"))
        self._current.set("Deal ticket", str(execution.deal_ticket or "—"))
        self._current.set("Position id", str(execution.position_id or "—"))
        self._current.set(
            "Requested / filled",
            f"{execution.requested_volume:.2f} / {execution.filled_volume:.2f}",
        )
        self._current.set("Retcode", str(execution.retcode or "—"))
        self._current.set("Message", execution.message or "—")
        self._current.set("Created", str(execution.created_at or "—"))
        self._current.set("Updated", str(execution.updated_at or "—"))

        account = snapshot.account
        self._policy.set("Run mode", snapshot.mode.name)
        if account is None:
            self._policy.set("Account type", "no account", PALETTE.muted)
        else:
            self._policy.set(
                "Account type",
                "DEMO" if account.is_demo else "NOT DEMO",
                PALETTE.ok if account.is_demo else PALETTE.danger,
            )
        self._policy.set("Real accounts", "blocked unconditionally", PALETTE.ok)
        self._policy.set("Order boundary", "core.execution only", PALETTE.text_dim)
        self._policy.set(
            "Arming",
            "two actions required"
            if snapshot.mode == RunMode.DEMO_CONFIRM
            else "not applicable in this mode",
        )
        self._policy.set("Arm TTL", f"{config.execution.arm_ttl_seconds}s")
        self._policy.set(
            "Reconcile grace", f"{config.execution.reconcile_grace_seconds}s"
        )
        self._policy.set("Magic number", str(config.execution.magic))

        self._orders.clear_rows()
        self._orders.setRowCount(len(orders))
        for row, order in enumerate(orders):
            self._orders.set_cell(row, 0, str(order.ticket), mono=True)
            self._orders.set_cell(row, 1, order.symbol, mono=True)
            self._orders.set_cell(row, 2, order.state)
            self._orders.set_cell(
                row, 3, f"{order.volume_initial:.2f}", mono=True, align_right=True
            )
            self._orders.set_cell(
                row, 4, f"{order.volume_current:.2f}", mono=True, align_right=True
            )
            self._orders.set_cell(
                row, 5, f"{order.price_open:.5f}", mono=True, align_right=True
            )
        self._orders.fit_columns()
