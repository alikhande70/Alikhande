"""Health view — what this build knows, assumes, and has not proven.

This view exists because the project's central claim is that unverified numbers
should not be trusted, and the fastest way to break that claim is to hide the
build's own uncertainty behind a clean dashboard.

It surfaces three things a normal trading panel would not: every ``[ASSUMED]``
value with that label attached, an honest verification status per subsystem, and
whether what is being recorded right now counts as evidence at all.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...i18n import fmt_count, fmt_money, fmt_percent, fmt_price, t
from ...config import assumption_registry
from ...core.enums import RuntimeKind
from ...version import EDITION, RULE_VERSION, SCORING_VERSION, VERSION
from ..components import Card, KeyValue, StatusChip, label
from ..theme import PALETTE, SPACE, TYPE

# Each entry is (subsystem, status text, tone). Deliberately blunt: every line
# states what has actually been executed, not what is believed to work.
VERIFICATION = [
    ("Core engines", "unit tested and executed", "good"),
    ("Persistence", "tested against real sqlite3", "good"),
    ("Backtest replay", "executed end to end", "good"),
    ("Indicator agreement", "NOT verified against a terminal", "warning"),
    ("Live broker path", "NOT verified — needs Windows + MT5", "warning"),
    ("Strategy edge", "NOT established, and not claimed", "critical"),
]


class HealthView(QWidget):
    def __init__(self, config, runtime, persistence):
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

        top = QHBoxLayout()
        top.setSpacing(SPACE.md)

        session = Card(t("health.session"))
        self._session = KeyValue(150)
        for key in (
            t("health.field.build"),
            t("health.field.rule"),
            t("health.field.scoring"),
            t("health.field.runtime"),
            t("health.field.evidence"),
            t("health.field.database"),
            t("health.field.gateway"),
            t("health.field.passes"),
            t("health.field.passtime"),
            t("health.field.news"),
        ):
            self._session.row(key)
        self._session.stretch()
        session.add(self._session)
        top.addWidget(session, 1)

        verification = Card(t("health.verification"))
        for name, status, tone in VERIFICATION:
            row = QHBoxLayout()
            row.setSpacing(SPACE.md)
            row.addWidget(label(name, "Body"))
            row.addStretch(1)
            icon = {"good": "✓", "warning": "!", "critical": "✕"}[tone]
            row.addWidget(StatusChip(icon, status, tone))
            verification.add_layout(row)
        verification.add(
            label(
                "Anything marked NOT verified has not been executed. "
                "See docs/VERIFICATION.md for the full accounting.",
                "Caption",
            )
        )
        verification.body().addStretch(1)
        top.addWidget(verification, 1)

        root.addLayout(top)

        middle = QHBoxLayout()
        middle.setSpacing(SPACE.md)

        assumptions = Card(t("health.assumptions"))
        assumptions.add(
            label(
                "[ASSUMED] is a working default that has not been validated against "
                "a live broker. [POLICY] is a project decision, enforced structurally.",
                "Caption",
            )
        )
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Parameter", "Value", "Kind"])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setDefaultSectionSize(34)

        registry = assumption_registry()
        table.setRowCount(len(registry))
        for row, entry in enumerate(registry):
            assumed = entry["kind"] == "ASSUMED"
            for column, (text, colour, mono) in enumerate(
                (
                    (entry["key"], None, True),
                    (str(entry["value"]), None, True),
                    (entry["kind"], PALETTE.warning if assumed else PALETTE.accent, False),
                )
            ):
                item = QTableWidgetItem(text)
                if colour:
                    from PySide6.QtGui import QColor

                    item.setForeground(QColor(colour))
                if mono:
                    from PySide6.QtGui import QFont

                    item.setFont(QFont(PALETTE.mono.split(",")[0].strip("'"), TYPE.small))
                if column == 1:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                table.setItem(row, column, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        assumptions.add(table, 1)
        middle.addWidget(assumptions, 1)

        events = Card(t("health.journal"))
        events.add(
            label(
                "Repeated events are counted rather than repeated — a refusal logged "
                "every 250 ms is the same as no log at all.",
                "Caption",
            )
        )
        self._journal = QPlainTextEdit()
        self._journal.setReadOnly(True)
        self._journal.setMaximumBlockCount(400)
        events.add(self._journal, 1)
        middle.addWidget(events, 1)

        root.addLayout(middle, 1)
        self._render_static(runtime, persistence)

    def _render_static(self, runtime, persistence) -> None:
        self._session.set(t("health.field.build"), f"{VERSION} — {EDITION}")
        self._session.set(t("health.field.rule"), RULE_VERSION)
        self._session.set(t("health.field.scoring"), SCORING_VERSION)
        self._session.set(t("health.field.runtime"), f"{runtime.kind.name} ({runtime.description})")

        production = runtime.kind == RuntimeKind.LIVE
        self._session.set(
            t("health.field.evidence"),
            "yes — production history" if production else "NO — not production data",
            PALETTE.good if production else PALETTE.warning,
        )
        self._session.set(
            t("health.field.database"),
            persistence.filename if persistence.enabled else f"disabled — {persistence.rationale}",
            PALETTE.ink_secondary if persistence.enabled else PALETTE.ink_muted,
        )

    def update_view(self, snapshot, journal_entries=None) -> None:
        live = snapshot.runtime.kind == RuntimeKind.LIVE
        self._session.set(
            t("health.field.gateway"),
            ("connected" if snapshot.connected else "not connected")
            if live
            else "no broker — synthetic data",
            PALETTE.good if (live and snapshot.connected) else PALETTE.warning,
        )
        self._session.set(t("health.field.passes"), f"{snapshot.passes:,}")
        self._session.set(t("health.field.passtime"), f"{snapshot.last_pass_ms:.1f} ms")
        self._session.set(
            t("health.field.news"),
            "NONE — this run is news-blind" if snapshot.news_blind else "active",
            PALETTE.warning if snapshot.news_blind else PALETTE.good,
        )

        entries = snapshot.journal_entries if journal_entries is None else journal_entries
        text = "\n".join(event.format() for event in entries[-120:])
        if text != self._journal.toPlainText():
            self._journal.setPlainText(text)
            bar = self._journal.verticalScrollBar()
            bar.setValue(bar.maximum())
