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

from PySide6.QtCore import QObject, QThread, Signal

from ..app.engine import ScanEngine
from ..core.enums import RunMode


@dataclass
class Action:
    kind: str  # arm | confirm | acknowledge | reconnect | disarm | mode | configure
    payload: str = ""
    mode: RunMode = RunMode.ALERT_ONLY
    # Carried only by ``configure``. Typed loosely so a settings change follows
    # the same one-way queue as every other operator intent rather than
    # reaching into the engine from the GUI thread — which is the rule this
    # whole module exists to hold.
    config: object = None


class ScanWorker(QObject):
    """Runs ``ScanEngine`` on its own thread and emits snapshots."""

    snapshot_ready = Signal(object)
    action_result = Signal(str, bool, str)  # kind, ok, reason
    failed = Signal(str)

    def __init__(self, engine: ScanEngine, interval_ms: int) -> None:
        super().__init__()
        self._engine = engine
        self._interval_ms = max(50, interval_ms)
        self._actions: Queue[Action] = Queue()
        self._running = False
        self._initialised = False

    def enqueue(self, action: Action) -> None:
        """Called from the UI thread. ``Queue`` is the thread-safe hand-off."""
        self._actions.put(action)

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        try:
            # The connection is established HERE, on the worker thread, and
            # never by whoever constructed the gateway. The MetaTrader5 package
            # stamps an owner thread on attach and refuses calls from any
            # other, so connecting on the UI thread made every subsequent pass
            # raise — silently, because the engine swallows gateway errors, so
            # the window showed "disconnected" against a perfectly healthy
            # terminal.
            self._connect()

            while self._running:
                now = self._now()
                if not self._initialised:
                    self._engine.initialize(now)
                    self._initialised = True

                self._drain_actions(now)
                snapshot = self._engine.run_pass(self._now())
                self.snapshot_ready.emit(snapshot)
                QThread.msleep(self._interval_ms)
        except Exception as error:  # a dead worker must not fail silently
            self.failed.emit(f"{type(error).__name__}: {error}")

    def _connect(self) -> None:
        """Attach the gateway on this thread. Failure is reported, not raised.

        A gateway that cannot attach still produces passes — the engine reports
        `connected=False` and every view renders the offline state it already
        knows how to render. Raising here would kill the worker and leave a
        window that never updates again, which is strictly worse than a window
        that says it has no broker.
        """
        connect = getattr(self._engine.gateway, "ensure_connected", None)
        if connect is None:
            return
        try:
            connect()
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")

    def reconnect(self) -> bool:
        """Re-attach on this thread. Called from the action queue, never
        directly by the UI — see the thread rule above."""
        rebind = getattr(self._engine.gateway, "reconnect", None)
        if rebind is None:
            return False
        try:
            return bool(rebind())
        except Exception:
            return False

    def _now(self) -> int:
        """The engine's clock, falling back to local time only to keep turning.

        A gateway that cannot state the time cannot be traded against, but the
        UI still has to render something. Local time here only advances the
        loop; every gate that matters refuses without a fresh tick anyway.
        """
        import time

        return self._engine.server_time(fallback=int(time.time()))

    def _drain_actions(self, now: int) -> None:
        while True:
            try:
                action = self._actions.get_nowait()
            except Empty:
                return

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
                ok = self.reconnect()
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
            else:
                ok, reason = False, f"UNKNOWN_ACTION({action.kind})"

            self.action_result.emit(action.kind, ok, reason)
