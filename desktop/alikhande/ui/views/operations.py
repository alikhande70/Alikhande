"""Operations view — the link, the data, the record, and the recovery tools.

Everything an operator needs on the day something is wrong, in one place. The
subsystems behind it were built to be testable without a terminal; this is
where they become usable without one either.

Four panels, ordered by how urgently they are usually needed:

**Link and data.** Connection health with its latency and availability, and the
symbols whose data has been chronically unusable. The second of those is the
one no other screen can show: a symbol failing its bar count once is a symbol
still downloading, and the same symbol failing four hundred times over two days
is a symbol the broker does not serve on that timeframe. Only the accumulated
record can tell them apart.

**Session history.** Whether the last shutdown was one, and what was in flight
when it was not.

**The journal.** Searchable, because a de-duplicated ring of five hundred events
is only useful if you can find the one you want in it.

**Recovery.** Backup, restore, settings export/import, diagnostics bundle.

## Why restore asks twice

Restoring the wrong snapshot is a mistake an operator makes exactly once, at
the worst possible moment. The underlying call already refuses to overwrite —
it moves the current database aside to a timestamped name and deletes nothing
ever — but a confirmation is still cheaper than explaining afterwards where the
file went.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.dataquality import severity_of
from ...core.journal import Level
from ...core.recovery import ExitKind
from ...core.supervision import summarise
from ...i18n import code as code_text
from ...i18n import fmt_count, fmt_percent, t
from ..components import Card, EmptyState, KeyValue, StatusChip, label
from ..theme import PALETTE, SPACE, severity_colour

#: Journal level to (icon, severity). Colour never travels alone.
LEVEL_PRESENTATION = {
    Level.DEBUG: ("·", "unknown"),
    Level.INFO: ("·", "unknown"),
    Level.WARN: ("!", "warning"),
    Level.ERROR: ("✕", "critical"),
}


class OperationsView(QWidget):
    backup_requested = Signal()
    restore_requested = Signal(str)
    diagnostics_requested = Signal()
    export_settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list = []
        self._query = ""

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

        root.addLayout(self._build_link_and_data())
        root.addLayout(self._build_sessions_and_recovery())
        root.addWidget(self._build_journal(), 1)

    # ------------------------------------------------------------ link/data
    def _build_link_and_data(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACE.md)

        link = Card(t("ops.link"))
        header = QHBoxLayout()
        self._link_chip = StatusChip("?", t("ops.link.unknown"), "unknown")
        header.addWidget(self._link_chip)
        header.addStretch(1)
        link.add_layout(header)
        self._link_fields = KeyValue(150)
        for key in ("ops.link.latency", "ops.link.peak", "ops.link.availability",
                    "ops.link.failures", "ops.link.probes"):
            self._link_fields.row(t(key))
        link.add(self._link_fields)
        # Without a trailing stretch Qt spreads spare height evenly between the
        # children, so the title drifts to the middle of a tall card and the
        # panel reads as three floating fragments rather than one block.
        link.body().addStretch(1)
        row.addWidget(link, 1)

        quality = Card(t("ops.data"))
        self._quality_empty = EmptyState(
            "✓", t("ops.data.clean.title"), t("ops.data.clean.body")
        )
        quality.add(self._quality_empty)
        self._quality = KeyValue(150)
        quality.add(self._quality)
        note = label(t("ops.data.note"), "Caption")
        note.setWordWrap(True)
        quality.add(note)
        quality.body().addStretch(1)
        row.addWidget(quality, 1)
        return row

    # ------------------------------------------------- sessions and recovery
    def _build_sessions_and_recovery(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACE.md)

        sessions = Card(t("ops.sessions"))
        self._sessions = KeyValue(150)
        sessions.add(self._sessions)
        sessions.body().addStretch(1)
        row.addWidget(sessions, 1)

        recovery = Card(t("ops.recovery"))
        self._recovery_status = label(t("ops.recovery.idle"), "Caption")
        self._recovery_status.setWordWrap(True)
        recovery.add(self._recovery_status)

        buttons = QHBoxLayout()
        buttons.setSpacing(SPACE.sm)
        self._backup = QPushButton(t("ops.backup.now"))
        self._backup.setObjectName("Primary")
        self._backup.clicked.connect(self.backup_requested.emit)
        buttons.addWidget(self._backup)

        self._diagnostics = QPushButton(t("ops.diagnostics"))
        self._diagnostics.setObjectName("Ghost")
        self._diagnostics.clicked.connect(self.diagnostics_requested.emit)
        buttons.addWidget(self._diagnostics)

        self._export = QPushButton(t("ops.settings.export"))
        self._export.setObjectName("Ghost")
        self._export.clicked.connect(self.export_settings_requested.emit)
        buttons.addWidget(self._export)
        buttons.addStretch(1)
        recovery.add_layout(buttons)

        recovery.add(label(t("ops.backups"), "CardTitle"))
        self._backups_empty = EmptyState(
            "◷", t("ops.backups.empty.title"), t("ops.backups.empty.body")
        )
        recovery.add(self._backups_empty)
        self._backups = KeyValue(200)
        recovery.add(self._backups)

        restore_row = QHBoxLayout()
        restore_row.setSpacing(SPACE.sm)
        self._restore_path = QLineEdit()
        self._restore_path.setPlaceholderText(t("ops.restore.placeholder"))
        restore_row.addWidget(self._restore_path, 1)
        self._restore = QPushButton(t("ops.restore"))
        self._restore.setObjectName("Ghost")
        self._restore.clicked.connect(self._on_restore)
        restore_row.addWidget(self._restore)
        recovery.add_layout(restore_row)
        recovery.body().addStretch(1)
        row.addWidget(recovery, 2)
        return row

    def _on_restore(self) -> None:
        path = self._restore_path.text().strip()
        if not path:
            return
        # The call underneath already moves the current database aside rather
        # than overwriting it. This is still cheaper than explaining afterwards
        # where the file went.
        answer = QMessageBox.question(
            self,
            t("ops.restore.confirm.title"),
            t("ops.restore.confirm.body", path=path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restore_requested.emit(path)

    # --------------------------------------------------------------- journal
    def _build_journal(self) -> QWidget:
        card = Card(t("ops.journal"))
        search = QHBoxLayout()
        search.setSpacing(SPACE.sm)
        self._search = QLineEdit()
        self._search.setPlaceholderText(t("ops.journal.search"))
        self._search.textChanged.connect(self._on_search)
        search.addWidget(self._search, 1)
        self._journal_count = label("", "Caption")
        search.addWidget(self._journal_count)
        card.add_layout(search)

        self._journal = QPlainTextEdit()
        self._journal.setReadOnly(True)
        self._journal.setMinimumHeight(220)
        card.add(self._journal, 1)
        return card

    def _on_search(self, text: str) -> None:
        self._query = text.strip().lower()
        self._render_journal()

    def _render_journal(self) -> None:
        if self._query:
            matched = [
                e
                for e in self._entries
                if self._query in e.code.lower()
                or self._query in e.message.lower()
                or self._query in e.context.lower()
            ]
        else:
            matched = self._entries

        # Newest first. A journal read top-down when the thing you are looking
        # for just happened is a journal you scroll to the bottom of every time.
        lines = [
            f"{e.level.name:<5} {e.context or '-':<10} {e.code}: {e.message}"
            + (f"  (x{e.repeats + 1})" if e.repeats else "")
            for e in reversed(matched)
        ]
        self._journal.setPlainText("\n".join(lines))
        self._journal_count.setText(
            t("ops.journal.count", shown=fmt_count(len(matched)),
              total=fmt_count(len(self._entries)))
        )

    # ---------------------------------------------------------------- update
    def update_view(self, *, link=None, quality=None, sessions=None, journal=None) -> None:
        if link is not None:
            summary = summarise(link)
            self._link_chip.set(
                {"good": "✓", "warning": "!", "serious": "!", "critical": "✕"}.get(
                    summary.severity, "?"
                ),
                code_text(summary.code),
                summary.severity,
            )
            for key, value in (
                ("ops.link.latency", summary.fields["latency"]),
                ("ops.link.peak", summary.fields["peak"]),
                ("ops.link.availability", summary.fields["availability"]),
                ("ops.link.failures", summary.fields["failures"]),
                ("ops.link.probes", summary.fields["probes"]),
            ):
                self._link_fields.set(t(key), value)

        if quality is not None:
            chronic = [q for q in quality.values() if q.chronic]
            self._quality.clear()
            self._quality_empty.setVisible(not chronic)
            for record in sorted(chronic, key=lambda q: (-q.bad_fraction, q.symbol)):
                severity, _key = severity_of(record.grade)
                summary = t(
                    "ops.data.chronic",
                    fraction=fmt_percent(record.bad_fraction * 100.0, 0),
                    passes=fmt_count(record.passes),
                )
                self._quality.row(record.symbol, summary, mono=False)
                # A second call only to carry the colour; `row` has no colour
                # parameter and giving it one would push presentation into a
                # component that deliberately has none.
                self._quality.set(record.symbol, summary, severity_colour(severity))

        if sessions is not None:
            self._sessions.clear()
            # Newest first, and bounded — this panel is a summary, not the
            # archive. The full list is in the diagnostics bundle.
            for record in list(reversed(sessions))[:8]:
                kind = record.exit_kind
                colour = (
                    PALETTE.good
                    if kind == ExitKind.CLEAN
                    else severity_colour("critical" if record.execution_in_flight else "warning")
                )
                name = record.session_id[:8] or "—"
                self._sessions.row(name, "", mono=False)
                self._sessions.set(
                    name,
                    t(f"ops.exit.{kind.name.lower()}")
                    + (f"  ·  {record.in_flight_symbol}" if record.execution_in_flight else ""),
                    colour,
                )

        if journal is not None:
            self._entries = list(journal)
            self._render_journal()

    def set_recovery_status(self, message: str, severity: str = "good") -> None:
        self._recovery_status.setText(message)
        self._recovery_status.setStyleSheet(f"color: {severity_colour(severity)};")

    def set_backups(self, paths: list) -> None:
        self._backups.clear()
        self._backups_empty.setVisible(not paths)
        for path in paths[:6]:
            self._backups.row(path.name, "", mono=False)
            self._backups.set(path.name, t("ops.backups.size", kb=fmt_count(
                max(1, path.stat().st_size // 1024))))
