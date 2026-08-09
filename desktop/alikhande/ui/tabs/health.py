"""Health tab — what this build knows, assumes, and has not proven.

This tab exists because the project's central claim is that unverified numbers
should not be trusted, and the fastest way to break that claim is to hide the
build's own uncertainty behind a clean dashboard.

So it surfaces three things a normal trading panel would not:

* **The assumption registry** — every ``[ASSUMED]`` value, with that label on
  it, so the operator can go and check the ones that matter to them.
* **The verification status** — which parts have been executed and which have
  only been reasoned about.
* **The runtime and persistence routing** — whether what is being recorded
  right now counts as evidence at all.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...config import assumption_registry
from ...core.enums import RuntimeKind
from ...version import EDITION, RULE_VERSION, SCORING_VERSION, VERSION
from ..theme import PALETTE
from ..widgets import Card, KeyValue, Table


class HealthTab(QWidget):
    def __init__(self, config, runtime, persistence) -> None:
        super().__init__()
        self._config = config

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(PALETTE.gap)

        top = QHBoxLayout()
        top.setSpacing(PALETTE.gap)

        session = Card("Session")
        self._session = KeyValue()
        for key in (
            "Build",
            "Rule version",
            "Scoring version",
            "Runtime",
            "Counts as evidence",
            "Database",
            "Gateway",
            "Passes",
            "Pass time",
            "News filtering",
        ):
            self._session.row(key)
        self._session.stretch()
        session.add(self._session)
        top.addWidget(session, 1)

        verification = Card("Verification status")
        self._verification = KeyValue()
        for key in (
            "Core engines",
            "Persistence",
            "Backtest replay",
            "Indicator agreement",
            "Live broker path",
            "Strategy edge",
        ):
            self._verification.row(key)
        self._verification.stretch()
        verification.add(self._verification)
        top.addWidget(verification, 1)

        root.addLayout(top)
        self._render_static(runtime, persistence)

        middle = QHBoxLayout()
        middle.setSpacing(PALETTE.gap)

        assumptions = Card("Assumption registry")
        table = Table(["Parameter", "Value", "Kind"])
        registry = assumption_registry()
        table.setRowCount(len(registry))
        for row, entry in enumerate(registry):
            table.set_cell(row, 0, entry["key"], mono=True)
            table.set_cell(row, 1, str(entry["value"]), mono=True, align_right=True)
            table.set_cell(
                row,
                2,
                entry["kind"],
                PALETTE.warning if entry["kind"] == "ASSUMED" else PALETTE.accent,
            )
        table.fit_columns()
        assumptions.add(table, 1)
        middle.addWidget(assumptions, 1)

        events = Card("Event journal")
        self._journal = QPlainTextEdit()
        self._journal.setReadOnly(True)
        self._journal.setMaximumBlockCount(400)
        events.add(self._journal, 1)
        middle.addWidget(events, 1)

        root.addLayout(middle, 1)

    def _render_static(self, runtime, persistence) -> None:
        self._session.set("Build", f"{VERSION} — {EDITION}")
        self._session.set("Rule version", RULE_VERSION)
        self._session.set("Scoring version", SCORING_VERSION)
        self._session.set("Runtime", f"{runtime.kind.name} ({runtime.description})")

        production = runtime.kind == RuntimeKind.LIVE
        self._session.set(
            "Counts as evidence",
            "yes — production history" if production else "NO — not production data",
            PALETTE.ok if production else PALETTE.warning,
        )
        self._session.set(
            "Database",
            persistence.filename if persistence.enabled else f"disabled ({persistence.rationale})",
            PALETTE.text_dim if persistence.enabled else PALETTE.muted,
        )

        # Deliberately blunt. Each line states what has actually been executed,
        # not what is believed to work.
        self._verification.set("Core engines", "unit tested and executed", PALETTE.ok)
        self._verification.set("Persistence", "unit tested against real sqlite3", PALETTE.ok)
        self._verification.set("Backtest replay", "executed end to end", PALETTE.ok)
        self._verification.set(
            "Indicator agreement",
            "NOT verified against a terminal",
            PALETTE.warning,
        )
        self._verification.set(
            "Live broker path",
            "NOT verified — needs Windows + MT5",
            PALETTE.warning,
        )
        self._verification.set(
            "Strategy edge",
            "NOT established, and not claimed",
            PALETTE.danger,
        )

    def update_view(self, snapshot, journal) -> None:
        self._session.set(
            "Gateway",
            "connected" if snapshot.connected else "not connected",
            PALETTE.ok if snapshot.connected else PALETTE.danger,
        )
        self._session.set("Passes", f"{snapshot.passes:,}")
        self._session.set("Pass time", f"{snapshot.last_pass_ms:.1f} ms")
        self._session.set(
            "News filtering",
            "NONE — this run is news-blind" if snapshot.news_blind else "active",
            PALETTE.warning if snapshot.news_blind else PALETTE.ok,
        )

        lines = []
        for event in journal.recent(120):
            lines.append(event.format())
        text = "\n".join(lines)
        if text != self._journal.toPlainText():
            self._journal.setPlainText(text)
            scrollbar = self._journal.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
