"""The application window.

Composition only: it wires a gateway to an engine to a worker to five views, and
owns no scanner logic of its own. Everything it displays came from a snapshot
the worker produced.

The shell is a **left navigation rail** rather than a tab strip. Tabs imply peers
of equal weight; these are not peers. The Dashboard is where the operator lives,
Signal is where they go to check a claim, and Risk / Execution / Health are
consulted. A rail gives the primary destination room to say so, and leaves space
for a live count beside "Signals" so an opportunity is visible from any view.

The one piece of judgement that lives here is the **real-account banner**. When
the attached account is not a demo, a red bar takes the top of the window and
the mode selector locks to Alert-only. The refusal is enforced three layers down
and does not depend on this bar existing — the bar is here so the operator is
never surprised by it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..app.engine import ScanEngine
from ..config import AppConfig
from ..core.calendar_gate import CalendarGate
from ..core.enums import RunMode, RuntimeKind
from ..core.journal import Journal
from ..core.runtime import detect_runtime, persistence_plan
from ..core.statistics import Statistics
from ..version import VERSION
from .components import NavItem, StatusChip, label
from .theme import PALETTE, SPACE, stylesheet
from .views.dashboard import DashboardView
from .views.execution import ExecutionView
from .views.health import HealthView
from .views.risk import RiskView
from .views.signal import SignalView
from .worker import Action, ScanWorker

NAV = [
    ("◈", "Dashboard", "What is happening right now"),
    ("◎", "Signal", "One symbol, with the structure it is built on"),
    ("◔", "Risk", "Exposure against its limits, and the evidence base"),
    ("◆", "Execution", "The in-flight order and its reconciliation"),
    ("◇", "Health", "What this build has and has not proven"),
]


def data_directory() -> Path:
    """Where the database and logs live.

    ``%LOCALAPPDATA%`` on Windows, XDG elsewhere. Deliberately not beside the
    executable: a PyInstaller bundle may sit in Program Files, which a normal
    user cannot write to, and a scanner that silently fails to persist is a
    scanner with no evidence.
    """
    import os

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / "AlikhandeScanner"
    path.mkdir(parents=True, exist_ok=True)
    return path


class MainWindow(QMainWindow):
    def __init__(self, engine: ScanEngine, config: AppConfig, runtime, persistence, repositories):
        super().__init__()
        self._engine = engine
        self._config = config
        self._repo = repositories
        self._statistics = Statistics(repositories, config.statistics)

        self.setWindowTitle(f"Alikhande Scanner {VERSION}")
        self.resize(1560, 960)
        self.setMinimumSize(1180, 720)

        plane = QWidget()
        plane.setObjectName("Plane")
        shell = QHBoxLayout(plane)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        shell.addWidget(self._build_sidebar())

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._build_topbar())

        self._banner = self._build_banner()
        right.addWidget(self._banner)
        self._banner.setVisible(False)

        self._stack = QStackedWidget()
        self._dashboard = DashboardView(config, self._statistics)
        self._signal = SignalView(config, self._statistics)
        self._risk = RiskView(config, repositories)
        self._execution = ExecutionView(config)
        self._health = HealthView(config, runtime, persistence)
        for view in (self._dashboard, self._signal, self._risk, self._execution, self._health):
            self._stack.addWidget(view)
        right.addWidget(self._stack, 1)

        container = QWidget()
        container.setLayout(right)
        shell.addWidget(container, 1)
        self.setCentralWidget(plane)

        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background: {PALETTE.surface}; border-top: 1px solid "
            f"{PALETTE.border}; color: {PALETTE.ink_muted}; }}"
        )
        self.statusBar().showMessage("starting…")

        self._dashboard.symbol_activated.connect(self._focus_symbol)
        self._signal.arm_requested.connect(lambda s: self._post(Action("arm", s)))
        self._signal.confirm_requested.connect(lambda s: self._post(Action("confirm", s)))
        self._execution.acknowledge_requested.connect(
            lambda note: self._post(Action("acknowledge", note))
        )

        self._start_worker()

    # ------------------------------------------------------------------ shell
    def _build_sidebar(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("Sidebar")
        rail.setFixedWidth(228)

        column = QVBoxLayout(rail)
        column.setContentsMargins(SPACE.md, SPACE.lg, SPACE.md, SPACE.lg)
        column.setSpacing(SPACE.xs)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand.addWidget(label("ALIKHANDE", "Brand"))
        brand.addWidget(label(f"SCANNER  ·  {VERSION}", "BrandSub"))
        column.addLayout(brand)
        column.addSpacing(SPACE.xl)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_items: list[NavItem] = []
        for index, (icon, name, tip) in enumerate(NAV):
            item = NavItem(icon, name)
            item.setToolTip(tip)
            item.clicked.connect(lambda _=False, i=index: self._stack.setCurrentIndex(i))
            self._nav_group.addButton(item, index)
            self._nav_items.append(item)
            column.addWidget(item)
        self._nav_items[0].setChecked(True)

        column.addStretch(1)

        column.addWidget(label("MODE", "CardTitle"))
        self._mode = QComboBox()
        self._mode.addItem("Alert only", RunMode.ALERT_ONLY)
        self._mode.addItem("Shadow", RunMode.SHADOW)
        self._mode.addItem("Demo · arm + confirm", RunMode.DEMO_CONFIRM)
        self._mode.currentIndexChanged.connect(self._on_mode_change)
        column.addWidget(self._mode)

        column.addSpacing(SPACE.md)
        self._chip_runtime = StatusChip("◆", "STARTING", "unknown")
        self._chip_account = StatusChip("○", "NO ACCOUNT", "unknown")
        for chip in (self._chip_runtime, self._chip_account):
            column.addWidget(chip)
        return rail

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(66)

        row = QHBoxLayout(bar)
        row.setContentsMargins(SPACE.xl, SPACE.sm, SPACE.xl, SPACE.sm)
        row.setSpacing(SPACE.md)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self._title = label(NAV[0][1], "ViewTitle")
        self._subtitle = label(NAV[0][2], "ViewSubtitle")
        titles.addWidget(self._title)
        titles.addWidget(self._subtitle)
        row.addLayout(titles)
        row.addStretch(1)

        self._chip_execution = StatusChip("○", "IDLE", "neutral")
        self._chip_pass = StatusChip("◷", "—", "neutral")
        row.addWidget(self._chip_pass)
        row.addWidget(self._chip_execution)

        self._stack_titles_connected = False
        return bar

    def _build_banner(self) -> QFrame:
        banner = QFrame()
        banner.setStyleSheet(
            f"background: {PALETTE.critical_wash}; border-bottom: 1px solid "
            f"{PALETTE.critical};"
        )
        row = QHBoxLayout(banner)
        row.setContentsMargins(SPACE.xl, SPACE.md, SPACE.xl, SPACE.md)
        row.setSpacing(SPACE.md)
        icon = QLabel("✕")
        icon.setStyleSheet(f"color: {PALETTE.critical}; font-size: 16px;")
        self._banner_text = label("", "Body")
        self._banner_text.setWordWrap(True)
        self._banner_text.setStyleSheet(f"color: {PALETTE.critical}; font-weight: 600;")
        row.addWidget(icon)
        row.addWidget(self._banner_text, 1)
        return banner

    # ----------------------------------------------------------------- worker
    def _start_worker(self) -> None:
        self._thread = QThread(self)
        self._worker = ScanWorker(self._engine, self._config.scan.scan_interval_ms)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.snapshot_ready.connect(self._on_snapshot)
        self._worker.action_result.connect(self._on_action_result)
        self._worker.failed.connect(self._on_worker_failed)
        self._stack.currentChanged.connect(self._on_view_changed)
        self._thread.start()

    def _post(self, action: Action) -> None:
        self._worker.enqueue(action)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)

    # ---------------------------------------------------------------- signals
    def _on_view_changed(self, index: int) -> None:
        icon, name, tip = NAV[index]
        self._title.setText(name)
        self._subtitle.setText(tip)
        if index < len(self._nav_items):
            self._nav_items[index].setChecked(True)

    def _focus_symbol(self, symbol: str) -> None:
        self._signal.select(symbol)
        self._stack.setCurrentIndex(1)

    def _on_mode_change(self, index: int) -> None:
        self._post(Action("mode", mode=self._mode.itemData(index)))

    def _on_action_result(self, kind: str, ok: bool, reason: str) -> None:
        if ok:
            self.statusBar().showMessage(
                {
                    "arm": "Plan armed — confirm to send.",
                    "confirm": "Order submitted.",
                    "acknowledge": "Unresolved execution cleared.",
                    "mode": "Run mode changed.",
                }.get(kind, "done"),
                6000,
            )
            return

        self.statusBar().showMessage(f"{kind} refused: {reason}", 10000)
        if kind != "mode":
            return

        # A refused mode change must not leave the selector showing a mode the
        # engine is not in — that discrepancy is exactly how somebody ends up
        # believing they armed something.
        self._sync_mode(self._engine.mode)
        if reason == "REAL_ACCOUNT_BLOCKED":
            QMessageBox.critical(
                self,
                "Real account",
                "This build refuses to trade a non-demo account.\n\n"
                "The refusal is structural: there is no setting, no input and no "
                "mode that reaches a live account.",
            )
        elif reason == "PERSISTENCE_REQUIRED_FOR_DEMO_EXECUTION":
            QMessageBox.warning(
                self,
                "No database",
                "Demo execution needs persistence.\n\nWithout it there is no "
                "de-duplication across restarts and no durable record of an "
                "in-flight order, which is precisely what restart recovery "
                "depends on.",
            )

    def _sync_mode(self, mode: RunMode) -> None:
        index = self._mode.findData(mode)
        if index >= 0 and index != self._mode.currentIndex():
            self._mode.blockSignals(True)
            self._mode.setCurrentIndex(index)
            self._mode.blockSignals(False)

    def _on_worker_failed(self, message: str) -> None:
        self._chip_runtime.set("✕", "WORKER STOPPED", "critical")
        self.statusBar().showMessage(f"scan worker stopped: {message}")
        QMessageBox.critical(
            self,
            "Scan worker stopped",
            f"The scan loop raised and stopped:\n\n{message}\n\n"
            "No further scanning or execution will happen until the application "
            "is restarted.",
        )

    # ---------------------------------------------------------------- render
    def _on_snapshot(self, snapshot) -> None:
        account = snapshot.account
        live = snapshot.runtime.kind == RuntimeKind.LIVE

        # The chips must never imply a broker that is not there. An offline
        # session's gateway reports "connected" — to its own synthetic series —
        # and its account is a fabricated demo with login 0. Rendering that as
        # "connected / DEMO 0" is exactly the kind of plausible-looking
        # falsehood this project exists to refuse.
        if not live:
            self._chip_runtime.set("!", f"{snapshot.runtime.kind.name} · NO BROKER", "warning")
            self._chip_runtime.setToolTip(
                "No MetaTrader terminal is attached. Prices are synthetic and nothing "
                "here describes a real market."
            )
            self._chip_account.set("!", "SIMULATED", "warning")
        else:
            self._chip_runtime.set(
                "✓" if snapshot.connected else "✕",
                "CONNECTED" if snapshot.connected else "DISCONNECTED",
                "good" if snapshot.connected else "critical",
            )
            if account is None:
                self._chip_account.set("?", "NO ACCOUNT", "unknown")
            elif account.is_demo:
                self._chip_account.set("✓", f"DEMO {account.login}", "good")
            else:
                self._chip_account.set("✕", "REAL — BLOCKED", "critical")

        self._chip_execution.set(
            "✕" if snapshot.requires_manual_review else "○",
            snapshot.execution_state,
            "critical"
            if snapshot.requires_manual_review
            else ("warning" if snapshot.execution_state not in ("IDLE", "COMPLETED") else "neutral"),
        )
        self._chip_pass.set("◷", f"{snapshot.last_pass_ms:.0f} ms", "neutral")

        # ---- banner ----------------------------------------------------------
        if account is not None and not account.is_demo and live:
            self._banner_text.setText(
                f"REAL ACCOUNT DETECTED ({account.login} @ {account.server}). Execution is "
                "blocked unconditionally and the mode selector is locked to Alert-only. "
                "This build never trades a live account."
            )
            self._banner.setVisible(True)
            self._mode.setEnabled(False)
            self._sync_mode(RunMode.ALERT_ONLY)
        elif snapshot.requires_manual_review:
            self._banner_text.setText(
                "An execution could not be reconciled against the broker. Submission is "
                "blocked until it is reviewed and acknowledged on the Execution view."
            )
            self._banner.setVisible(True)
            self._mode.setEnabled(True)
        else:
            self._banner.setVisible(False)
            self._mode.setEnabled(True)

        # ---- nav badge -------------------------------------------------------
        actionable = [
            v
            for v in snapshot.symbols
            if v.resolved and v.plan is not None and v.plan.valid and not v.news_blocks
        ]
        self._nav_items[1].set_badge(len(actionable))

        # ---- views -----------------------------------------------------------
        evidence = 0
        if self._repo is not None and self._repo.ready:
            evidence = int(self._repo.outcome_summary()["total"])

        self._dashboard.update_view(snapshot, evidence)
        self._signal.update_view(snapshot)

        positions = self._engine.own_positions()
        self._risk.update_view(
            snapshot, positions, self._engine.exposure_summary(account), self._engine.guard_state
        )
        self._execution.update_view(
            snapshot, self._engine.execution.current, self._engine.working_orders()
        )
        self._health.update_view(snapshot, self._engine.journal)

        self.statusBar().showMessage(
            f"pass {snapshot.passes:,}  ·  {snapshot.last_pass_ms:.1f} ms  ·  "
            f"{snapshot.runtime.description}  ·  open risk {snapshot.exposure_open_pct:.2f}%"
        )


def build_application(offline: bool = False):
    """Assemble everything. Separated from ``run_application`` so a test can
    construct the window without entering the Qt event loop."""
    config = AppConfig()
    journal = Journal()

    gateway = None
    connected = False
    if not offline:
        try:
            from ..adapters.mt5.gateway import MT5Gateway

            candidate = MT5Gateway()
            candidate.connect()
            gateway = candidate
            connected = True
        except Exception as error:
            journal.warn("MT5_UNAVAILABLE", "", str(error), 0)

    if gateway is None:
        from ..adapters.offline.gateway import OfflineGateway
        from ..app.backtest import BACKTEST_TIMEFRAMES

        synthetic = OfflineGateway()
        synthetic.load_synthetic(config.symbols, BACKTEST_TIMEFRAMES, 400)
        synthetic.set_cursor(
            synthetic.series_length(config.symbols[0], BACKTEST_TIMEFRAMES[0])
        )
        gateway = synthetic
        connected = False

    runtime = detect_runtime(
        connected=connected, replay=False, identity_seed=str(data_directory())
    )
    persistence = persistence_plan(runtime, data_directory())

    repositories = None
    if persistence.enabled:
        try:
            from ..adapters.sqlite.database import Database
            from ..adapters.sqlite.repositories import Repositories

            database = Database()
            database.open(persistence.filename)
            repositories = Repositories(database)
            journal.set_sink(repositories.log_event)
        except Exception as error:
            journal.error("DB_OPEN_FAILED", persistence.filename, str(error), 0)
            if persistence.required:
                raise

    engine = ScanEngine(
        gateway,
        config,
        runtime=runtime,
        journal=journal,
        repositories=repositories,
        calendar=CalendarGate(None, config.news, journal),
    )

    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Alikhande Scanner")
    application.setStyleSheet(stylesheet())
    application.setWindowIcon(_icon())

    window = MainWindow(engine, config, runtime, persistence, repositories)
    return application, window


def _icon() -> QIcon:
    """A generated mark, so the bundle has no external asset to lose."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(PALETTE.surface_high))
    painter.setPen(QColor(PALETTE.accent))
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QColor(PALETTE.accent))
    font = painter.font()
    font.setPixelSize(34)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "A")
    painter.end()
    return QIcon(pixmap)


def run_application(offline: bool = False) -> int:
    application, window = build_application(offline=offline)
    window.show()
    return application.exec()
