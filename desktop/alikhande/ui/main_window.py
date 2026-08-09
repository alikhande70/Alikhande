"""The application window.

Composition only: it wires a gateway to an engine to a worker to five tabs, and
owns no scanner logic of its own. Everything it displays came from a snapshot
the worker produced.

The one piece of judgement that lives here is the **real-account banner**. When
the attached account is not a demo, a red bar takes the top of the window and
the mode selector is locked to Alert-only. The refusal itself is enforced three
layers down and does not depend on this bar existing — the bar is there so the
operator is never surprised by it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
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
from ..version import EDITION, VERSION
from .tabs.detail import DetailTab
from .tabs.execution import ExecutionTab
from .tabs.health import HealthTab
from .tabs.overview import OverviewTab
from .tabs.risk import RiskTab
from .theme import PALETTE, stylesheet
from .widgets import Pill
from .worker import Action, ScanWorker


def data_directory() -> Path:
    """Where the database and logs live.

    ``%LOCALAPPDATA%`` on Windows, XDG on everything else. Deliberately not
    beside the executable: a PyInstaller bundle may sit in Program Files, which
    is not writable by a normal user, and a scanner that silently fails to
    persist is a scanner with no evidence.
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
    def __init__(self, engine: ScanEngine, config: AppConfig, runtime, persistence) -> None:
        super().__init__()
        self._engine = engine
        self._config = config
        self._statistics = Statistics(None, config.statistics)

        self.setWindowTitle(f"Alikhande Scanner — {VERSION} {EDITION}")
        self.resize(1520, 940)

        root = QWidget()
        root.setObjectName("Root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())
        self._banner = self._build_banner()
        layout.addWidget(self._banner)
        self._banner.setVisible(False)

        self._tabs = QTabWidget()
        self._overview = OverviewTab(self._statistics, config.scoring.score_threshold)
        self._detail = DetailTab(self._statistics)
        self._risk = RiskTab(config, getattr(engine, "_repo", None))
        self._execution = ExecutionTab()
        self._health = HealthTab(config, runtime, persistence)

        self._tabs.addTab(self._overview, "Overview")
        self._tabs.addTab(self._detail, "Signal Detail")
        self._tabs.addTab(self._risk, "Risk")
        self._tabs.addTab(self._execution, "Execution")
        self._tabs.addTab(self._health, "Health")
        layout.addWidget(self._tabs, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("starting…")

        self._overview.symbol_activated.connect(self._focus_symbol)
        self._detail.arm_requested.connect(
            lambda symbol: self._post(Action("arm", symbol))
        )
        self._detail.confirm_requested.connect(
            lambda symbol: self._post(Action("confirm", symbol))
        )
        self._execution.acknowledge_requested.connect(
            lambda note: self._post(Action("acknowledge", note))
        )

        self._start_worker()

    # ------------------------------------------------------------------ chrome
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(58)

        row = QHBoxLayout(header)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(12)

        title = QLabel("ALIKHANDE SCANNER")
        title.setObjectName("AppTitle")
        version = QLabel(f"{VERSION} · {EDITION}")
        version.setObjectName("AppVersion")

        row.addWidget(title)
        row.addWidget(version)
        row.addSpacing(20)

        mode_label = QLabel("Mode")
        mode_label.setObjectName("Caption")
        self._mode = QComboBox()
        self._mode.addItem("Alert only", RunMode.ALERT_ONLY)
        self._mode.addItem("Shadow", RunMode.SHADOW)
        self._mode.addItem("Demo · arm + confirm", RunMode.DEMO_CONFIRM)
        self._mode.currentIndexChanged.connect(self._on_mode_change)
        row.addWidget(mode_label)
        row.addWidget(self._mode)

        row.addStretch(1)

        self._pill_connection = Pill("connecting", "warn")
        self._pill_account = Pill("no account", "")
        self._pill_runtime = Pill("—", "")
        self._pill_execution = Pill("IDLE", "")
        for pill in (
            self._pill_runtime,
            self._pill_connection,
            self._pill_account,
            self._pill_execution,
        ):
            row.addWidget(pill)
        return header

    def _build_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("Banner")
        row = QHBoxLayout(banner)
        row.setContentsMargins(16, 10, 16, 10)
        self._banner_text = QLabel()
        self._banner_text.setObjectName("BannerText")
        self._banner_text.setWordWrap(True)
        row.addWidget(self._banner_text)
        return banner

    # ------------------------------------------------------------------ worker
    def _start_worker(self) -> None:
        self._thread = QThread(self)
        self._worker = ScanWorker(self._engine, self._config.scan.scan_interval_ms)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.snapshot_ready.connect(self._on_snapshot)
        self._worker.action_result.connect(self._on_action_result)
        self._worker.failed.connect(self._on_worker_failed)
        self._thread.start()

    def _post(self, action: Action) -> None:
        self._worker.enqueue(action)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)

    # ----------------------------------------------------------------- signals
    def _on_mode_change(self, index: int) -> None:
        self._post(Action("mode", mode=self._mode.itemData(index)))

    def _focus_symbol(self, symbol: str) -> None:
        self._detail.select(symbol)
        self._tabs.setCurrentWidget(self._detail)

    def _on_action_result(self, kind: str, ok: bool, reason: str) -> None:
        if ok:
            message = {
                "arm": "Plan armed — confirm to send.",
                "confirm": "Order submitted.",
                "acknowledge": "Unresolved execution cleared.",
                "mode": "Run mode changed.",
            }.get(kind, "done")
            self.statusBar().showMessage(message, 6000)
            return

        self.statusBar().showMessage(f"{kind} refused: {reason}", 10000)
        if kind == "mode":
            # A refused mode change must not leave the selector showing a mode
            # the engine is not in — that discrepancy is exactly how somebody
            # ends up believing they armed something.
            self._sync_mode_selector(self._engine.mode)
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

    def _sync_mode_selector(self, mode: RunMode) -> None:
        index = self._mode.findData(mode)
        if index >= 0 and index != self._mode.currentIndex():
            self._mode.blockSignals(True)
            self._mode.setCurrentIndex(index)
            self._mode.blockSignals(False)

    def _on_worker_failed(self, message: str) -> None:
        self._pill_connection.set("worker stopped", "danger")
        self.statusBar().showMessage(f"scan worker stopped: {message}")
        QMessageBox.critical(
            self,
            "Scan worker stopped",
            f"The scan loop raised and stopped:\n\n{message}\n\n"
            "No further scanning or execution will happen until the application "
            "is restarted.",
        )

    def _on_snapshot(self, snapshot) -> None:
        account = snapshot.account

        live = snapshot.runtime.kind == RuntimeKind.LIVE
        self._pill_runtime.set(snapshot.runtime.kind.name, "ok" if live else "warn")

        # The connection and account pills must never imply a broker that is not
        # there. An offline session's gateway reports "connected" — to its own
        # synthetic series — and its account is a fabricated demo with login 0.
        # Rendering those as "connected / DEMO 0" is exactly the kind of
        # plausible-looking falsehood this project exists to refuse.
        if not live:
            self._pill_connection.set("no broker", "warn")
            self._pill_account.set("SIMULATED", "warn")
        else:
            self._pill_connection.set(
                "connected" if snapshot.connected else "disconnected",
                "ok" if snapshot.connected else "danger",
            )
            if account is None:
                self._pill_account.set("no account", "warn")
            elif account.is_demo:
                self._pill_account.set(f"DEMO {account.login}", "ok")
            else:
                self._pill_account.set("REAL — BLOCKED", "danger")

        self._pill_execution.set(
            snapshot.execution_state,
            "danger"
            if snapshot.requires_manual_review
            else ("warn" if snapshot.execution_state not in ("IDLE", "COMPLETED") else ""),
        )

        # ---- banner ----------------------------------------------------------
        if account is not None and not account.is_demo:
            self._banner_text.setText(
                f"REAL ACCOUNT DETECTED ({account.login} @ {account.server}). "
                "Execution is blocked unconditionally and the mode selector is locked "
                "to Alert-only. This build never trades a live account."
            )
            self._banner.setVisible(True)
            self._mode.setEnabled(False)
            self._sync_mode_selector(RunMode.ALERT_ONLY)
        elif snapshot.requires_manual_review:
            self._banner_text.setText(
                "An execution could not be reconciled against the broker. Submission is "
                "blocked until it is reviewed and acknowledged on the Execution tab."
            )
            self._banner.setVisible(True)
            self._mode.setEnabled(True)
        else:
            self._banner.setVisible(False)
            self._mode.setEnabled(True)

        # ---- tabs ------------------------------------------------------------
        self._overview.update_view(snapshot)
        self._detail.update_view(snapshot)

        positions = self._engine._own_positions()  # noqa: SLF001 - snapshot-adjacent read
        exposure = self._engine._risk.exposure(  # noqa: SLF001
            "",
            positions,
            self._engine._specs,  # noqa: SLF001
            account.equity if account and account.equity > 0 else 1.0,
        )
        self._risk.update_view(
            snapshot, positions, exposure, self._engine._account_guard.state  # noqa: SLF001
        )
        self._execution.update_view(
            snapshot,
            self._engine.execution.current,
            self._engine._safe_orders(),  # noqa: SLF001
            self._config,
        )
        self._health.update_view(snapshot, self._engine.journal)

        self.statusBar().showMessage(
            f"pass {snapshot.passes:,} · {snapshot.last_pass_ms:.1f} ms · "
            f"{snapshot.runtime.description} · open risk {snapshot.exposure_open_pct:.2f}%"
        )


def build_application(offline: bool = False) -> tuple[QApplication, MainWindow]:
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

        offline_gateway = OfflineGateway()
        offline_gateway.load_synthetic(config.symbols, BACKTEST_TIMEFRAMES, 400)
        offline_gateway.set_cursor(offline_gateway.series_length(config.symbols[0], BACKTEST_TIMEFRAMES[0]))
        gateway = offline_gateway
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

    window = MainWindow(engine, config, runtime, persistence)
    window._statistics = Statistics(repositories, config.statistics)
    return application, window


def _icon() -> QIcon:
    """A generated mark, so the bundle has no external asset to lose."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    from PySide6.QtGui import QColor, QPainter

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(PALETTE.surface_high))
    painter.setPen(QColor(PALETTE.accent))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
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
