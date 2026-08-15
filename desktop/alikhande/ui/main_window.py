"""The application window.

Composition only: it wires a gateway to an engine to a worker to the views, and
owns no scanner logic of its own. Everything it displays came from a snapshot
the worker produced, and the ranking on the landing screen comes from
``app.scanner`` rather than from a widget.

The shell is a **left navigation rail** rather than a tab strip. Tabs imply peers
of equal weight; these are not peers. The Scanner is where the operator lives —
it is the first thing on screen and answers the only question worth asking on
launch — Signal is where they go to check a claim it made, and Risk / Execution
/ Health are consulted. A rail gives the primary destination room to say so, and
leaves space for a live count beside it so an opportunity is visible from any
view.

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
from ..app.maintenance import (
    backup_database,
    diagnostics,
    export_settings,
    list_backups,
    load_sessions,
    prune_backups,
    restore_database,
    save_sessions,
    write_diagnostics,
)
from ..config import AppConfig
from ..i18n import (
    LANGUAGES,
    code,
    current,
    fmt_count,
    fmt_percent,
    is_rtl,
    load_preferences,
    save_preferences,
    set_language,
    t,
)
from ..core.calendar_gate import CalendarGate
from ..core.enums import DataState, RunMode, RuntimeKind, Timeframe
from ..core.journal import Journal
from ..core.dataquality import DataQualityMonitor
from ..core.environment import Environment
from ..core.notifications import NotificationRouter, Urgency
from ..core.recovery import SessionLedger, SessionRecord
from ..core.robot import Robot, RobotPolicy, minute_of_day
from ..core.runtime import detect_runtime, environment_plan
from ..core.supervision import ConnectionSupervisor, Probe
from ..core.statistics import Statistics
from ..version import VERSION
from ..profiles import Overrides, Profile, configure
from .components import EnvironmentPill, LiveDot, NavItem, StatusChip, label
from .theme import PALETTE, SPACE, active_theme, set_theme, stylesheet
from .views.backtest import BacktestView
from .views.dashboard import DashboardView
from .views.execution import ExecutionView
from .views.guide import GuideView
from .views.health import HealthView
from .views.operations import OperationsView
from .views.risk import RiskView
from .views.robot import RobotView
from .views.scanner import ScannerView
from .views.settings import SettingsView
from .views.signal import SignalView
from .worker import Action, ScanWorker

# Icon, translation key, tooltip key. The labels are looked up at render time
# rather than stored, so switching language relabels the rail without a restart.
#
# Scanner leads because it is what the window opens on, and this order is the
# order of the stack: index 0 is the landing screen. Everything after it is
# somewhere you go to check a claim the scanner made.
NAV = [
    ("scanner", "nav.scanner", "nav.scanner.tip"),
    ("dashboard", "nav.dashboard", "nav.dashboard.tip"),
    ("signal", "nav.signal", "nav.signal.tip"),
    ("risk", "nav.risk", "nav.risk.tip"),
    ("execution", "nav.execution", "nav.execution.tip"),
    ("robot", "nav.robot", "nav.robot.tip"),
    ("backtest", "nav.backtest", "nav.backtest.tip"),
    ("health", "nav.health", "nav.health.tip"),
    ("diagnostics", "nav.ops", "nav.ops.tip"),
    ("settings", "nav.settings", "nav.settings.tip"),
    ("guide", "nav.guide", "nav.guide.tip"),
]

# Referenced by name rather than as literals, because the two indices other
# code jumps to both moved when Scanner was inserted, and a stale number opens
# the wrong view without erroring.
VIEW_SCANNER = 0
VIEW_SIGNAL = 2
VIEW_GUIDE = len(NAV) - 1


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
        self._repo = repositories

        # The preset is restored before anything is built, because it decides
        # the thresholds every view then renders against. Loading it afterwards
        # would show one pass of the wrong numbers, which on a screen whose job
        # is to be believed is worse than a slower start.
        preferences = load_preferences(data_directory())
        self._profile = Profile.parse(preferences.get("profile"))
        self._overrides = Overrides.from_dict(preferences.get("overrides"))
        self._config = configure(
            config, self._profile, self._overrides, self._outcome_summary()
        )
        self._statistics = Statistics(repositories, self._config.statistics)

        # ---- the operational subsystems ------------------------------------
        # Built before the views, because several of them are rendered on the
        # first pass and a view holding None for its subsystem would have to
        # guard every read.
        self._supervisor = ConnectionSupervisor()
        self._quality = DataQualityMonitor()
        self._notifications = NotificationRouter(minimum_urgency=Urgency.NOTABLE)
        self._robot = Robot(RobotPolicy(**(preferences.get("robot") or {})))

        # The session ledger is opened here rather than at first pass, so a
        # crash during startup is still recorded as one.
        # A per-run identity. ``runtime.session_identity`` is a hash of the data
        # directory and is therefore the *same string every launch*, which made
        # the session history eight rows all called E1F87784 — unreadable, and
        # useless for saying which run crashed.
        import time as _time
        import uuid as _uuid

        started = int(_time.time())
        self._sessions = SessionLedger(load_sessions(data_directory()))
        self._recovery = self._sessions.open(
            SessionRecord(
                session_id=_uuid.uuid4().hex[:8].upper(),
                environment=engine.environment,
                version=VERSION,
                started_at=started,
            )
        )

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

        self._runtime = runtime
        self._persistence = persistence
        self._stack = QStackedWidget()
        self._build_views()
        right.addWidget(self._stack, 1)

        container = QWidget()
        container.setLayout(right)
        shell.addWidget(container, 1)
        self.setCentralWidget(plane)

        self.statusBar().showMessage(t("status.starting"))

        self._install_shortcuts()
        self._start_worker()
        self._report_recovery()

    # ------------------------------------------------------------------ views
    def _build_views(self) -> None:
        """Construct every view and wire its signals.

        Separated from ``__init__`` so a language or theme change can throw
        them away and build them again. Rebuilding is the honest way to
        retranslate and re-skin: threading a ``retranslate()`` through every
        card title, table header and key-value row means one forgotten label
        sits in the wrong language forever, and the forgotten one is always the
        rarely-seen warning that matters most.

        The views are pure renderers over a snapshot, so nothing is lost — the
        next scan pass repopulates them within one interval.
        """
        while self._stack.count():
            widget = self._stack.widget(0)
            # The backtest view owns a worker thread. Dropping the widget while
            # that thread runs leaves Qt destroying a live QThread, so give it a
            # chance to stop first — a language or theme switch can land here at
            # any moment, including mid-replay.
            shutdown = getattr(widget, "shutdown", None)
            if callable(shutdown):
                shutdown()
            self._stack.removeWidget(widget)
            widget.deleteLater()

        self._scanner = ScannerView(self._config)
        self._dashboard = DashboardView(self._config, self._statistics)
        self._signal = SignalView(self._config, self._statistics)
        self._risk = RiskView(self._config, self._repo)
        self._execution = ExecutionView(self._config)
        self._backtest = BacktestView(
            self._config,
            self._persistence.filename if self._persistence.enabled else "",
        )
        self._robot_view = RobotView(self._robot.policy)
        self._health = HealthView(self._config, self._runtime, self._persistence)
        self._operations = OperationsView()
        self._settings = SettingsView(
            self._config,
            self._profile,
            self._overrides,
            active_theme().name,
            self._outcome_summary(),
        )
        self._guide = GuideView()

        for view in (
            self._scanner,
            self._dashboard,
            self._signal,
            self._risk,
            self._execution,
            self._robot_view,
            self._backtest,
            self._health,
            self._operations,
            self._settings,
            self._guide,
        ):
            self._stack.addWidget(view)

        self._scanner.symbol_activated.connect(self._focus_symbol)
        self._settings.changed.connect(self._on_settings_changed)
        self._settings.theme_changed.connect(self._on_theme_change)
        self._dashboard.symbol_activated.connect(self._focus_symbol)
        self._signal.arm_requested.connect(lambda s: self._post(Action("arm", s)))
        self._signal.confirm_requested.connect(lambda s: self._post(Action("confirm", s)))
        self._execution.acknowledge_requested.connect(
            lambda note: self._post(Action("acknowledge", note))
        )
        self._robot_view.policy_changed.connect(self._on_robot_policy)
        self._robot_view.resume_requested.connect(self._robot.resume)
        self._operations.backup_requested.connect(self._run_backup)
        self._operations.restore_requested.connect(self._run_restore)
        self._operations.diagnostics_requested.connect(self._write_diagnostics)
        self._operations.export_settings_requested.connect(self._export_settings)


    def _on_environment_change(self, index: int) -> None:
        """Store the chosen environment and say when it takes effect.

        Deliberately **not** applied to the running session. Switching
        environments changes which database accumulates the evidence and which
        execution engine the orders would go through, and doing that under a
        live session would either mix two environments' records in one file or
        silently orphan an in-flight execution in the one being left.

        Neither is worth the convenience of not restarting. So the preference
        is written, the window says so plainly, and the change lands on the
        next launch — which is also when the persistence routing is decided.
        """
        chosen = self._environment.itemData(index)
        if not chosen or chosen == self._engine.environment:
            return
        self._save_preferences()
        QMessageBox.information(
            self,
            t("shell.environment"),
            t("env.restart", environment=t(f"env.{chosen.lower()}")),
        )

    # ------------------------------------------------- operational subsystems
    def _observe_link(self, snapshot) -> None:
        """Turn this pass into one health probe.

        The pass duration stands in for round-trip latency. It is not a pure
        measurement — it includes the analysis — but it is monotonic in the
        thing being measured and it needs no extra call to the terminal, which
        a health check that itself hammers a struggling link would.
        """
        server_time = snapshot.now if snapshot.connected else 0
        self._supervisor.observe(
            Probe(
                ok=snapshot.connected,
                latency_ms=snapshot.last_pass_ms,
                server_time=server_time,
                detail="" if snapshot.connected else "gateway reported not connected",
            ),
            snapshot.now,
        )

        state = self._supervisor.health.state
        previous = getattr(self, "_last_link_state", None)
        if state != previous:
            self._last_link_state = state
            subject = {
                "HEALTHY": "link.restored",
                "DEGRADED": "link.degraded",
                "STALLED": "link.stalled",
                "DISCONNECTED": "link.disconnected",
            }[state.name]
            self._notify(subject, self._supervisor.health.detail, snapshot.now)

    def _record_quality(self, snapshot) -> None:
        """Grade each symbol's series from what the pass already carried.

        ``view.bars`` is a **display slice** — the engine copies the last 140
        M5 bars for the chart and analyses a much longer window it does not
        hand over. Grading that slice against the 300-bar analysis minimum
        reports every symbol as permanently unusable, which is what the first
        render of this panel did: four symbols, "unusable in 100% of 31
        passes", every one of them fine.

        So sufficiency is taken from the engine's own verdict — ``data_state``
        is READY exactly when the full window was there — and the slice is used
        for the two questions it can actually answer: is the series continuous,
        and is it current.
        """
        from ..core.dataquality import inspect_series

        for view in snapshot.symbols:
            if not view.resolved or not view.bars:
                continue
            ready = view.snapshot.data_state == DataState.READY
            required = len(view.bars) if ready else self._config.scan.minimum_bars
            series = inspect_series(
                view.symbol,
                Timeframe.M5,
                [bar.time for bar in view.bars],
                required=required,
                now=snapshot.now,
            )
            self._quality.record(view.symbol, [series], snapshot.now)

    def _drive_robot(self, snapshot) -> None:
        """One robot pass, and whatever it asked for."""
        weekday, minute = minute_of_day(snapshot.now) if snapshot.now else (0, 0)
        actionable = sum(
            1
            for v in snapshot.symbols
            if v.resolved and v.plan is not None and v.plan.valid and not v.news_blocks
        )
        decision = self._robot.evaluate(
            now=snapshot.now,
            weekday=weekday,
            minute_of_day=minute,
            environment=snapshot.environment,
            link_usable=self._supervisor.health.usable,
            data_usable=self._quality.worst_grade() <= 2,
            news_blocked=snapshot.news_blind,
            may_trade=snapshot.may_trade,
            execution_unresolved=self._engine.execution.has_unresolved(),
            candidates=actionable,
            armed_stale=bool(snapshot.armed_symbol) and snapshot.armed_seconds <= 0,
        )

        for subject, detail in decision.notify:
            self._notify(subject, detail, snapshot.now)

        # The robot decides; the app acts. That split is what keeps the robot
        # testable — but it only means anything if something on this side
        # actually carries the decisions out. For a while nothing did, so
        # `auto_reconnect` and `auto_disarm` were two checkboxes that changed
        # nothing at all.
        if decision.backup and self._persistence.enabled:
            self._run_backup(quiet=True)

        if decision.reconnect and self._supervisor.should_reconnect(snapshot.now):
            # Routed through the action queue because re-attaching must happen
            # on the worker thread, and gated by the supervisor's backoff so a
            # terminal that is down stays asked politely rather than every pass.
            self._supervisor.record_attempt(snapshot.now, succeeded=False)
            self._post(Action("reconnect"))

        if decision.disarm:
            self._post(Action("disarm", "ROBOT_STALE_INTENT"))

        self._robot_view.update_view(decision.status)

    def _now(self) -> int:
        """The broker's clock as of the last pass, or local time before one.

        Deliberately not `engine.server_time()`: that asks the gateway, and
        every caller of this method is on the UI thread. The last snapshot's
        timestamp is the same number the worker read, a few hundred
        milliseconds stale at most, and it costs no cross-thread call.
        """
        import time as _time

        return getattr(self, "_last_now", 0) or int(_time.time())

    def _report_recovery(self) -> None:
        """Say what happened to the previous session.

        This was computed at startup and then thrown away, which meant the
        entire recovery subsystem — crash detection, the in-flight flag, the
        distinction between "the app died" and "the app died holding an order"
        — produced a value nobody ever saw.

        A crash holding an unresolved execution is the one case that interrupts
        with a dialog rather than a status line. The submit gate is already
        shut and will stay shut across restarts; the operator needs to know why
        nothing will send before they go looking for a broken scanner.
        """
        verdict = self._recovery
        if verdict.quiet:
            return

        detail = t(f"recovery.{verdict.code.lower()}")
        if verdict.detail:
            detail = f"{detail} ({verdict.detail})"

        self._notify("session.crash_recovered", detail, self._now())

        if verdict.severity == "critical":
            QMessageBox.warning(self, t("recovery.title"), detail)

    def _notify(self, subject: str, detail: str, now: int) -> None:
        """Raise a notification and put it somewhere a human will find it.

        The router applies the policy — urgency, per-subject throttling — and
        used to be the end of the line: nothing consumed what survived it, so
        every notification in the application was a value assigned to a deque
        and forgotten.

        Two destinations now, and both are deliberate. The **journal** because
        it is persisted, searchable and already on screen, so a notification
        raised at three in the morning is still readable at nine. The **status
        bar** for anything at WARNING or above, because a row in a list nobody
        has opened is not an alert.
        """
        notification = self._notifications.notify(subject, detail, now=now)
        if notification is None:
            return

        message = f'{t(notification.title_key)}{f" — {detail}" if detail else ""}'
        if notification.urgency >= Urgency.WARNING:
            self._engine.journal.warn(subject.upper(), "", message, now)
            # 8 seconds: long enough to read, short enough that it does not sit
            # over the pass counter for the rest of the session.
            self.statusBar().showMessage(message, 8000)
        else:
            self._engine.journal.info(subject.upper(), "", message, now)

    # -------------------------------------------------------- operator actions
    def _on_robot_policy(self, policy) -> None:
        self._robot.configure(policy)
        self._save_preferences()

    def _backup_folder(self) -> Path:
        folder = data_directory() / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _run_backup(self, quiet: bool = False) -> None:
        if not self._persistence.enabled:
            return
        folder = self._backup_folder()
        result = backup_database(self._persistence.filename, folder)
        if result.ok:
            prune_backups(folder)
            self._operations.set_recovery_status(
                t("ops.backup.ok", path=result.path), "good"
            )
            if not quiet:
                self._notify("backup.written", result.path, self._now())
        else:
            self._operations.set_recovery_status(
                t("ops.backup.failed", error=result.error), "critical"
            )
            # Always notified, quiet or not. A scheduled backup that silently
            # failed for three weeks is the exact situation backups exist for.
            self._notify("backup.failed", result.error, self._now())
        self._operations.set_backups(list_backups(folder))

    def _run_restore(self, path: str) -> None:
        if not self._persistence.enabled:
            return
        result = restore_database(path, self._persistence.filename)
        if result.ok:
            self._operations.set_recovery_status(
                t("ops.restore.ok", path=result.displaced_to), "warning"
            )
            QMessageBox.information(
                self, t("ops.restore"), t("ops.restore.ok", path=result.displaced_to)
            )
        else:
            self._operations.set_recovery_status(
                t("ops.restore.failed", error=result.error), "critical"
            )
        self._operations.set_backups(list_backups(self._backup_folder()))

    def _write_diagnostics(self) -> None:
        bundle = diagnostics(
            version=VERSION,
            environment=self._engine.environment,
            data_dir=data_directory(),
            link=self._supervisor.health,
            quality=self._quality.symbols(),
            sessions=self._sessions.history(),
            errors=self._engine.execution.errors,
            # From the snapshot, not the gateway: this runs on the UI thread.
            account=getattr(self, "_last_account", None),
            journal_entries=self._engine.journal.recent(200),
        )
        path = write_diagnostics(bundle, data_directory() / "diagnostics")
        self._operations.set_recovery_status(t("ops.diagnostics.ok", path=path), "good")

    def _export_settings(self) -> None:
        path = export_settings(
            self._preferences_payload(),
            version=VERSION,
            path=data_directory() / "settings-export.json",
        )
        self._operations.set_recovery_status(t("ops.settings.ok", path=path), "good")

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
        self._brand = label(t("app.brand"), "Brand")
        self._brandsub = label(f'{t("app.brandsub")}  ·  {VERSION}', "BrandSub")
        brand.addWidget(self._brand)
        brand.addWidget(self._brandsub)
        column.addLayout(brand)
        column.addSpacing(SPACE.xl)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_items: list[NavItem] = []
        for index, (icon, key, tip) in enumerate(NAV):
            item = NavItem(icon, t(key))
            item.setToolTip(t(tip))
            item.clicked.connect(lambda _=False, i=index: self._stack.setCurrentIndex(i))
            self._nav_group.addButton(item, index)
            self._nav_items.append(item)
            column.addWidget(item)
        self._nav_items[0].setChecked(True)

        column.addStretch(1)

        # The environment sits above the mode, because it decides which modes
        # are selectable at all — offering DEMO_CONFIRM and then refusing it
        # would teach the operator to distrust the control.
        self._env_label = label(t("shell.environment"), "CardTitle")
        column.addWidget(self._env_label)
        self._environment = QComboBox()
        for name in Environment.ALL:
            self._environment.addItem(t(f"env.{name.lower()}"), name)
        self._environment.setCurrentIndex(
            self._environment.findData(self._engine.environment)
        )
        self._environment.currentIndexChanged.connect(self._on_environment_change)
        column.addWidget(self._environment)
        column.addSpacing(SPACE.md)

        self._mode_label = label(t("shell.mode"), "CardTitle")
        column.addWidget(self._mode_label)
        self._mode = QComboBox()
        self._mode.addItem(t("mode.alert"), RunMode.ALERT_ONLY)
        self._mode.addItem(t("mode.shadow"), RunMode.SHADOW)
        self._mode.addItem(t("mode.demo"), RunMode.DEMO_CONFIRM)
        self._mode.currentIndexChanged.connect(self._on_mode_change)
        column.addWidget(self._mode)

        column.addSpacing(SPACE.md)
        self._language_label = label(t("shell.language"), "CardTitle")
        column.addWidget(self._language_label)
        self._language = QComboBox()
        # Not `code`: that name is the translator imported at module scope, and
        # shadowing it here would silently break any later call in this method.
        for language_code, language in LANGUAGES.items():
            self._language.addItem(language.name, language_code)
        self._language.setCurrentIndex(self._language.findData(current().code))
        self._language.currentIndexChanged.connect(self._on_language_change)
        column.addWidget(self._language)

        column.addSpacing(SPACE.md)
        self._chip_runtime = StatusChip("◆", t("chip.starting"), "unknown")
        self._chip_account = StatusChip("○", t("chip.no_account"), "unknown")
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
        self._title = label(t(NAV[0][1]), "ViewTitle")
        self._subtitle = label(t(NAV[0][2]), "ViewSubtitle")
        titles.addWidget(self._title)
        titles.addWidget(self._subtitle)
        row.addLayout(titles)
        row.addStretch(1)

        # The environment reads before anything else on this bar, because it is
        # the single fact that changes what every other number on screen means.
        # A drawdown figure from a replay and one from a live demo account look
        # identical and are not the same claim.
        self._env_pill = EnvironmentPill()
        row.addWidget(self._env_pill)

        # A live indicator, next to the pass timing it corroborates. "3 ms" on
        # its own is equally consistent with a scanner running well and one
        # that stopped twenty minutes ago showing its last reading.
        self._live = LiveDot()
        row.addWidget(self._live)

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

    def _on_language_change(self, index: int) -> None:
        """Switch language and lay the whole window out again.

        Qt applies ``setLayoutDirection`` down the widget tree, so the mirroring
        is free for standard widgets. Custom-painted ones decide for themselves:
        the bar breakdown mirrors, and the price chart deliberately does not —
        right-to-left flips reading order, not time, and a mirrored candle chart
        would show an uptrend as a downtrend to anybody who has seen one before.
        """
        code = self._language.itemData(index)
        set_language(code)
        application = QApplication.instance()
        if application is not None:
            application.setLayoutDirection(
                Qt.LayoutDirection.RightToLeft if is_rtl() else Qt.LayoutDirection.LeftToRight
            )
        self._retranslate()
        self._save_preferences()

    def _retranslate(self) -> None:
        """Relabel everything the shell owns; views relabel their own chrome on
        the next snapshot, which arrives within one scan interval."""
        self.setWindowTitle(f'{t("app.title")} {VERSION}')
        self._brand.setText(t("app.brand"))
        self._brandsub.setText(f'{t("app.brandsub")}  ·  {VERSION}')
        self._mode_label.setText(t("shell.mode"))
        self._language_label.setText(t("shell.language"))

        for index, (icon, key, tip) in enumerate(NAV):
            self._nav_items[index].relabel(icon, t(key))
            self._nav_items[index].setToolTip(t(tip))

        self._mode.blockSignals(True)
        for index, key in enumerate(("mode.alert", "mode.shadow", "mode.demo")):
            self._mode.setItemText(index, t(key))
        self._mode.blockSignals(False)

        # The picker has to agree with the language actually in force. It
        # normally does, because it is what caused the change — but it is also
        # the one control that can be out of step after the language is set
        # from somewhere else, and a picker showing the wrong language is a
        # small thing that makes the whole window look untrustworthy.
        self._language.blockSignals(True)
        index = self._language.findData(current().code)
        if index >= 0:
            self._language.setCurrentIndex(index)
        self._language.blockSignals(False)

        selected = self._stack.currentIndex()
        selected_symbol = getattr(self._signal, "_symbol", "")
        self._build_views()
        if 0 <= selected < self._stack.count():
            self._stack.setCurrentIndex(selected)
        if selected_symbol:
            self._signal.select(selected_symbol)
        self._on_view_changed(self._stack.currentIndex())

    def _install_shortcuts(self) -> None:
        """Keyboard access to every view, plus language and quit.

        A trading panel that can only be driven by mouse is slower than the
        market at exactly the wrong moments.
        """
        from PySide6.QtGui import QKeySequence, QShortcut

        for index in range(len(NAV)):
            QShortcut(
                QKeySequence(f"Ctrl+{index + 1}"),
                self,
                lambda i=index: self._stack.setCurrentIndex(i),
            )
        QShortcut(QKeySequence("Ctrl+L"), self, self._cycle_language)
        QShortcut(QKeySequence("F1"), self, lambda: self._stack.setCurrentIndex(VIEW_GUIDE))
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_picker)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    def _cycle_language(self) -> None:
        nxt = (self._language.currentIndex() + 1) % self._language.count()
        self._language.setCurrentIndex(nxt)

    def _focus_picker(self) -> None:
        self._stack.setCurrentIndex(VIEW_SIGNAL)
        self._signal._picker.setFocus()

    def _preferences_payload(self) -> dict:
        """Everything worth restoring next launch, in one place.

        Shared by the periodic save and by the settings export, so the two can
        never disagree about what a "setting" is — an export missing the robot
        policy would restore an operator onto a new machine with their
        automation silently switched off.
        """
        from dataclasses import asdict

        policy = self._robot.policy
        return {
            "language": current().code,
            "theme": active_theme().name,
            "profile": self._profile.value,
            "overrides": self._overrides.to_dict(),
            # The selector, not the engine: the operator's choice is what should
            # survive a restart, and the engine is still running the previous one.
            "environment": (
                self._environment.currentData()
                if hasattr(self, "_environment")
                else self._engine.environment
            ),
            "view": self._stack.currentIndex(),
            "width": self.width(),
            "height": self.height(),
            # Windows are dropped: they are dataclasses, and the reconstruction
            # on load would have to be version-tolerant for a value the
            # operator cannot yet edit. The permissions are what they change.
            "robot": {
                k: v for k, v in asdict(policy).items() if k != "windows"
            },
        }

    def _save_preferences(self) -> None:
        save_preferences(data_directory(), self._preferences_payload())

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._save_preferences()
        # Closing the ledger IS the shutdown path whose absence marks a crash.
        # It runs before the worker is stopped, so a hang in thread teardown
        # still leaves this session recorded as having closed cleanly.
        self._sessions.close(getattr(self, "_last_now", 0))
        save_sessions(self._sessions.history(), data_directory())
        self._backtest.shutdown()
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)

    # ---------------------------------------------------------------- signals
    def _on_view_changed(self, index: int) -> None:
        icon, key, tip = NAV[index]
        self._title.setText(t(key))
        self._subtitle.setText(t(tip))
        if index < len(self._nav_items):
            self._nav_items[index].setChecked(True)

    def _focus_symbol(self, symbol: str) -> None:
        self._signal.select(symbol)
        self._stack.setCurrentIndex(VIEW_SIGNAL)

    # -------------------------------------------------------------- preferences
    def _outcome_summary(self) -> dict:
        """The aggregate outcome record, or an empty dict with no database.

        Auto reads this to decide whether to tighten. An empty dict is the
        honest input on a fresh install, and ``profiles.auto_overrides``
        answers it with the defaults — Auto's opinion on no evidence is the
        same as Default's, which is the only defensible opinion to hold.
        """
        if self._repo is None or not getattr(self._repo, "ready", False):
            return {}
        return self._repo.outcome_summary()

    def _on_settings_changed(self) -> None:
        """Apply a preset change and push it to the engine.

        The engine is reconfigured through the worker queue like every other
        operator intent, so the swap happens between passes on the scan thread
        rather than underneath one from the GUI thread. A refusal comes back
        through ``_on_action_result`` and is shown; the views keep rendering
        the values they were built with until the engine confirms.
        """
        self._profile = self._settings.profile()
        self._overrides = self._settings.overrides()
        self._config = configure(
            self._config, self._profile, self._overrides, self._outcome_summary()
        )
        self._statistics = Statistics(self._repo, self._config.statistics)
        self._post(Action("configure", config=self._config))
        self._save_preferences()

    def _on_theme_change(self, name: str) -> None:
        """Switch palette, re-apply the stylesheet, rebuild the views.

        The rebuild is not laziness. Qt stylesheets are strings evaluated when
        applied, and every widget that painted itself with an inline
        ``setStyleSheet`` — chips, badges, the banner — captured colours from
        the old palette at construction. Re-applying the global sheet fixes the
        first group and leaves the second untouched, which is a worse result
        than either extreme.
        """
        set_theme(name)
        application = QApplication.instance()
        if application is not None:
            application.setStyleSheet(stylesheet())
        selected = self._stack.currentIndex()
        self._build_views()
        if 0 <= selected < self._stack.count():
            self._stack.setCurrentIndex(selected)
        self._save_preferences()

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
                    "configure": t("set.applied"),
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
        # Recorded so an offscreen render can wait for real data rather than
        # screenshotting the loading state.
        self._passes_seen = snapshot.passes
        # Kept so `closeEvent` can stamp the session with broker time rather
        # than the local clock, which every other timestamp in the ledger uses.
        self._last_now = snapshot.now
        # The last pass, held whole. The handful of UI-thread consumers that
        # run outside a pass — the diagnostics bundle, the recovery report,
        # a backup taken from a button — read what the worker last observed
        # rather than asking the gateway, which they are on the wrong thread
        # to do.
        self._last_snapshot = snapshot
        self._last_account = snapshot.account
        account = snapshot.account
        live = snapshot.runtime.kind == RuntimeKind.LIVE

        # The chips must never imply a broker that is not there. An offline
        # session's gateway reports "connected" — to its own synthetic series —
        # and its account is a fabricated demo with login 0. Rendering that as
        # "connected / DEMO 0" is exactly the kind of plausible-looking
        # falsehood this project exists to refuse.
        if not live:
            self._chip_runtime.set(
                "!", f'{code(snapshot.runtime.kind.name).upper()} · {t("chip.no_broker")}', "warning"
            )
            self._chip_runtime.setToolTip(t("chip.no_broker.tip"))
            self._chip_account.set("!", t("chip.simulated"), "warning")
        else:
            self._chip_runtime.set(
                "✓" if snapshot.connected else "✕",
                t("chip.connected") if snapshot.connected else t("chip.disconnected"),
                "good" if snapshot.connected else "critical",
            )
            if account is None:
                self._chip_account.set("?", t("chip.no_account"), "unknown")
            elif account.is_demo:
                self._chip_account.set("✓", f'{t("chip.demo")} {account.login}', "good")
            else:
                self._chip_account.set("✕", t("chip.real_blocked"), "critical")

        self._chip_execution.set(
            "✕" if snapshot.requires_manual_review else "○",
            code(snapshot.execution_state).upper(),
            "critical"
            if snapshot.requires_manual_review
            else ("warning" if snapshot.execution_state not in ("IDLE", "COMPLETED") else "neutral"),
        )
        self._chip_pass.set(
            "◷", f'{fmt_count(int(snapshot.last_pass_ms))} {t("unit.ms")}', "neutral"
        )

        # ---- environment and liveness ---------------------------------------
        self._env_pill.set(snapshot.environment, locked=bool(snapshot.send_lock))
        self._env_pill.setToolTip(t(f"env.{snapshot.environment.lower()}.tip"))

        # The dot pulses only while passes are actually landing. Pulsing on a
        # dead worker would make the indicator worse than nothing — it would be
        # actively asserting the one thing it exists to disprove.
        advancing = snapshot.passes != getattr(self, "_last_pass_count", -1)
        self._last_pass_count = snapshot.passes
        self._live.set_state(
            PALETTE.good if snapshot.connected else PALETTE.unknown, live=advancing
        )

        # ---- banner ----------------------------------------------------------
        if account is not None and not account.is_demo and live:
            self._banner_text.setText(
                t("banner.real", login=account.login, server=account.server)
            )
            self._banner.setVisible(True)
            self._mode.setEnabled(False)
            self._sync_mode(RunMode.ALERT_ONLY)
        elif snapshot.requires_manual_review:
            self._banner_text.setText(t("banner.review"))
            self._banner.setVisible(True)
            self._mode.setEnabled(True)
        else:
            self._banner.setVisible(False)
            self._mode.setEnabled(True)

        # ---- nav badge -------------------------------------------------------
        # On Scanner, not Signal: the badge answers "is there anything to look
        # at", and the screen that answers it is the one it should point to.
        actionable = [
            v
            for v in snapshot.symbols
            if v.resolved and v.plan is not None and v.plan.valid and not v.news_blocks
        ]
        self._nav_items[VIEW_SCANNER].set_badge(len(actionable))

        # ---- views -----------------------------------------------------------
        evidence = 0
        if self._repo is not None and self._repo.ready:
            evidence = int(self._repo.outcome_summary()["total"])

        self._scanner.update_snapshot(snapshot, self._repo)
        self._dashboard.update_view(snapshot, evidence)
        self._signal.update_view(snapshot)

        # Everything here comes off the snapshot. Asking the engine would ask
        # the gateway, and this method runs on the UI thread — the MetaTrader5
        # package refuses calls from any thread but the one that attached, so
        # those reads raised, were swallowed, and rendered as an account with no
        # positions and no exposure. The accessors that allowed it are gone.
        self._risk.update_view(
            snapshot, snapshot.positions, snapshot.exposure, self._engine.guard_state
        )
        self._execution.update_view(
            snapshot, self._engine.execution.current, snapshot.orders
        )
        self._health.update_view(snapshot, self._engine.journal)

        # ---- the operational subsystems, fed from this pass -----------------
        self._observe_link(snapshot)
        self._record_quality(snapshot)
        self._drive_robot(snapshot)

        self._operations.update_view(
            link=self._supervisor.health,
            quality=self._quality.symbols(),
            sessions=self._sessions.history(),
            journal=self._engine.journal.entries(),
        )

        # The in-flight flag is written every pass rather than at shutdown,
        # because its whole value is being correct at the moment the process
        # dies — and a process that dies does not run its shutdown path.
        in_flight = self._engine.execution.has_unresolved()
        self._sessions.mark_in_flight(snapshot.execution_message or "", in_flight)
        if in_flight != getattr(self, "_last_in_flight", None):
            self._last_in_flight = in_flight
            save_sessions(self._sessions.history(), data_directory())

        self.statusBar().showMessage(
            t(
                "status.pass",
                passes=fmt_count(snapshot.passes),
                ms=fmt_count(int(snapshot.last_pass_ms)),
                runtime=code(snapshot.runtime.kind.name),
                risk=fmt_percent(snapshot.exposure_open_pct),
            )
        )


def build_application(offline: bool = False, environment: str = ""):
    """Assemble everything. Separated from ``run_application`` so a test can
    construct the window without entering the Qt event loop.

    ``environment`` is the declared one. An empty string means "whatever the
    operator chose last", read from preferences — with one override that is not
    negotiable: an offline session is a BACKTEST no matter what is stored,
    because there is no terminal, and a window claiming to be in production
    while reading synthetic bars would be the single most misleading thing this
    application could put on screen.
    """
    config = AppConfig()
    journal = Journal()

    stored = load_preferences(data_directory())
    declared = Environment.parse(environment or stored.get("environment"))

    gateway = None
    connected = False
    if not offline:
        # Probe, do not connect. The probe attaches, reads and detaches again,
        # which answers the two questions this function needs — is a terminal
        # there, and is its account a demo — without leaving a connection
        # stamped with the UI thread as its owner. The real attachment happens
        # on the scan worker, in `ScanWorker._connect`.
        from ..adapters.mt5.gateway import MT5Gateway, probe_terminal

        probe = probe_terminal()
        if probe.available:
            gateway = MT5Gateway()
            connected = True
            journal.info(
                "MT5_AVAILABLE",
                "",
                f"terminal build {probe.build}, account {probe.login} @ {probe.server}",
                0,
            )
            if not probe.trade_allowed:
                journal.warn(
                    "ALGO_TRADING_DISABLED",
                    "",
                    "Algo Trading is off in the terminal; no order can be sent until "
                    "it is enabled in Tools -> Options -> Expert Advisors",
                    0,
                )
        else:
            journal.warn("MT5_UNAVAILABLE", "", probe.reason, 0)

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

    if not connected:
        declared = Environment.BACKTEST

    runtime = detect_runtime(
        connected=connected, replay=False, identity_seed=str(data_directory())
    )
    # Routed by the declared environment, not by the runtime kind. A demo
    # session and a production session are both RuntimeKind.LIVE and would
    # otherwise land in one file, which is exactly the contamination the
    # original routing exists to prevent.
    persistence = environment_plan(
        declared,
        data_directory(),
        session_identity=runtime.session_identity,
        connected=connected,
    )

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
        environment=declared,
    )

    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Alikhande Scanner")

    # Restore the operator's language and theme BEFORE the window is built, so
    # nothing is ever constructed with labels or colours it immediately has to
    # replace — and before the stylesheet, which reads the active palette.
    preferences = load_preferences(data_directory())
    set_language(preferences.get("language", "en"))
    set_theme(preferences.get("theme", "dark"))

    application.setStyleSheet(stylesheet())
    application.setWindowIcon(_icon())
    application.setLayoutDirection(
        Qt.LayoutDirection.RightToLeft if is_rtl() else Qt.LayoutDirection.LeftToRight
    )

    window = MainWindow(engine, config, runtime, persistence, repositories)
    width = int(preferences.get("width", 1560))
    height = int(preferences.get("height", 960))
    window.resize(max(1180, width), max(720, height))
    view = int(preferences.get("view", 0))
    if 0 <= view < window._stack.count():
        window._stack.setCurrentIndex(view)
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
