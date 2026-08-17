"""The scan worker thread.

**Every gateway call in the application happens on this thread and nowhere
else.** The ``MetaTrader5`` package keeps process-global connection state and is
not safe to call concurrently, so the discipline is absolute rather than
best-effort: the UI thread reads snapshots the worker produced and never
touches a gateway, an engine or a repository directly.

Operator actions (arm, confirm, acknowledge, change mode) are therefore queued
rather than executed inline. The UI posts an intent; the worker performs it at
the top of the next pass and reports back through a signal. That costs at most
one scan interval of latency and buys the guarantee that no broker call is ever
made from the GUI thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal

from ..app.engine import ScanEngine
from ..config import AppConfig
from ..core.enums import RunMode
from ..core.models import RuntimeContext
from ..core.runtime import PersistencePlan


@dataclass
class Action:
    kind: str  # arm | confirm | acknowledge | reconnect | disarm | mode | configure
    payload: object = ""
    mode: RunMode = RunMode.ALERT_ONLY
    # Carried only by ``configure``. Typed loosely so a settings change follows
    # the same one-way queue as every other operator intent rather than
    # reaching into the engine from the GUI thread — which is the rule this
    # whole module exists to hold.
    config: object = None


@dataclass(frozen=True)
class WorkerBootstrap:
    """Everything needed to build state on its owning thread.

    It contains descriptions and paths, never an open gateway or database
    handle. That distinction prevents composition on the GUI thread from
    accidentally becoming connection or repository access.
    """

    config: AppConfig
    runtime: RuntimeContext
    persistence: PersistencePlan
    environment: str
    calendar_path: str = ""
    offline: bool = False


class ScanWorker(QObject):
    """Runs ``ScanEngine`` on its own thread and emits snapshots."""

    snapshot_ready = Signal(object)
    action_result = Signal(str, bool, str)  # kind, ok, reason
    failed = Signal(str)

    def __init__(self, bootstrap: WorkerBootstrap, interval_ms: int) -> None:
        super().__init__()
        if not isinstance(bootstrap, WorkerBootstrap):
            raise TypeError("ScanWorker accepts descriptions only; live objects are worker-owned")
        self._engine: ScanEngine | None = None
        self._gateway = None
        self._bootstrap = bootstrap
        self._repositories = None
        self._interval_ms = max(50, interval_ms)
        self._actions: Queue[Action] = Queue()
        # Unlike `_running`, an Event cannot lose a stop requested just before
        # QThread invokes `run()`. Without it, an immediate window close could
        # set `_running=False`, then `run()` would overwrite that with True and
        # leave the owner thread alive after the UI had tried to join it.
        self._stop_requested = Event()
        self._running = False
        self._initialised = False

    def enqueue(self, action: Action) -> None:
        """Called from the UI thread. ``Queue`` is the thread-safe hand-off."""
        self._actions.put(action)

    def stop(self) -> None:
        self._stop_requested.set()
        self._running = False

    def run(self) -> None:
        self._running = True
        last_now = 0
        try:
            if self._stop_requested.is_set():
                return
            self._engine = self._build_engine()
            if self._stop_requested.is_set():
                return
            # The connection is established HERE, on the worker thread, and
            # never by whoever constructed the gateway. The MetaTrader5 package
            # stamps an owner thread on attach and refuses calls from any
            # other, so connecting on the UI thread made every subsequent pass
            # raise — silently, because the engine swallows gateway errors, so
            # the window showed "disconnected" against a perfectly healthy
            # terminal.
            self._connect()

            while self._running and not self._stop_requested.is_set():
                now = self._now()
                last_now = now
                if not self._initialised:
                    self._engine.initialize(now)
                    self._initialised = True

                snapshot = self._engine.run_pass(self._now())
                # Handle exactly one intent per freshly completed pass. Arm or
                # Confirm can therefore never act on a view left over from the
                # previous interval, or from a configuration change earlier in
                # the same queue drain.
                if self._handle_one_action(self._now()):
                    snapshot = self._engine.run_pass(self._now())
                self.snapshot_ready.emit(snapshot)
                QThread.msleep(self._interval_ms)
        except Exception as error:  # a dead worker must not fail silently
            self.failed.emit(f"{type(error).__name__}: {error}")
        finally:
            self._shutdown(last_now)

    def _build_engine(self) -> ScanEngine:
        """Create gateway, database and engine on the scan thread itself."""
        bootstrap = self._bootstrap

        from ..core.calendar_gate import CalendarGate, CsvCalendar
        from ..core.journal import Journal

        journal = Journal()
        if bootstrap.offline:
            from ..adapters.offline.gateway import OfflineGateway
            from ..app.backtest import BACKTEST_TIMEFRAMES

            gateway = OfflineGateway()
            gateway.load_synthetic(
                bootstrap.config.symbols, BACKTEST_TIMEFRAMES, 400
            )
            gateway.set_cursor(
                gateway.series_length(
                    bootstrap.config.symbols[0], BACKTEST_TIMEFRAMES[0]
                )
            )
        else:
            from ..adapters.mt5.gateway import MT5Gateway

            gateway = MT5Gateway()

        repositories = None
        persistence = bootstrap.persistence
        if persistence.enabled:
            from ..adapters.sqlite.database import Database
            from ..adapters.sqlite.repositories import Repositories

            database = Database()
            database.open(persistence.filename)
            repositories = Repositories(database)
            journal.set_sink(repositories.log_event)
        self._repositories = repositories
        self._gateway = gateway

        calendar_source = (
            CsvCalendar(bootstrap.calendar_path) if bootstrap.calendar_path else None
        )
        return ScanEngine(
            gateway,
            bootstrap.config,
            runtime=bootstrap.runtime,
            journal=journal,
            repositories=repositories,
            calendar=CalendarGate(calendar_source, bootstrap.config.news, journal),
            environment=bootstrap.environment,
        )

    def _shutdown(self, now: int) -> None:
        import time

        stamp = now or int(time.time())
        if self._engine is not None:
            try:
                self._engine.shutdown(stamp)
            except Exception as error:
                self.failed.emit(f"shutdown: {type(error).__name__}: {error}")
        shutdown = getattr(self._gateway, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass
        if self._repositories is not None:
            try:
                self._repositories.close()
            except Exception as error:
                self.failed.emit(f"database close: {type(error).__name__}: {error}")

    def _connect(self) -> None:
        """Attach the gateway on this thread. Failure is reported, not raised.

        A gateway that cannot attach still produces passes — the engine reports
        `connected=False` and every view renders the offline state it already
        knows how to render. Raising here would kill the worker and leave a
        window that never updates again, which is strictly worse than a window
        that says it has no broker.
        """
        assert self._engine is not None
        connect = getattr(self._gateway, "ensure_connected", None)
        if connect is None:
            return
        try:
            connect()
        except Exception as error:
            self._engine.journal.warn(
                "GATEWAY_CONNECT_FAILED",
                "",
                f"{type(error).__name__}: {error}",
                self._now(),
            )

    def _reconnect(self) -> bool:
        """Re-attach on this thread. Called from the action queue, never
        directly by the UI — see the thread rule above."""
        assert self._engine is not None
        rebind = getattr(self._gateway, "reconnect", None)
        if rebind is None:
            return False
        try:
            connected = bool(rebind())
            if connected:
                self._engine.refresh_gateway_state(self._now())
            return connected
        except Exception:
            return False

    def _now(self) -> int:
        """The engine's clock, falling back to local time only to keep turning.

        A gateway that cannot state the time cannot be traded against, but the
        UI still has to render something. Local time here only advances the
        loop; every gate that matters refuses without a fresh tick anyway.
        """
        import time

        assert self._engine is not None
        return self._engine.server_time(fallback=int(time.time()))

    def _handle_one_action(self, now: int) -> bool:
        assert self._engine is not None
        try:
            action = self._actions.get_nowait()
        except Empty:
            return False

        if action.kind == "arm":
            ok, reason = self._engine.arm(action.payload, now)
        elif action.kind == "confirm":
            ok, reason = self._engine.confirm(action.payload, now)
        elif action.kind == "acknowledge":
            ok = self._engine.acknowledge_unresolved(action.payload, now)
            reason = "" if ok else "NOT_AWAITING_REVIEW"
        elif action.kind == "reconnect":
            # Must happen on this thread: the gateway stamps an owner on
            # attach. That is why it arrives through the queue rather than
            # being called from wherever noticed the link was down.
            ok = self._reconnect()
            reason = "" if ok else "RECONNECT_FAILED"
        elif action.kind == "disarm":
            self._engine.arming.disarm(action.payload or "ROBOT", now)
            ok, reason = True, ""
        elif action.kind == "mode":
            ok, reason = self._engine.set_mode(action.mode, now)
        elif action.kind == "configure":
            if action.config is None:
                ok, reason = False, "NO_CONFIG"
            else:
                ok, reason = self._engine.reconfigure(action.config, now)
        elif action.kind == "journal":
            try:
                level, subject, message = action.payload
                writer = getattr(self._engine.journal, str(level), None)
                if not callable(writer):
                    raise ValueError(f"unknown journal level {level}")
                writer(str(subject), "", str(message), now)
                ok, reason = True, ""
            except (TypeError, ValueError) as error:
                ok, reason = False, f"INVALID_JOURNAL_ACTION({error})"
        else:
            ok, reason = False, f"UNKNOWN_ACTION({action.kind})"

        if action.kind != "journal":
            self.action_result.emit(action.kind, ok, reason)
        return True
