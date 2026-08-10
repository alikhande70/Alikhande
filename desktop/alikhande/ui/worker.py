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
    kind: str  # arm | confirm | acknowledge | mode
    payload: str = ""
    mode: RunMode = RunMode.ALERT_ONLY


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
            elif action.kind == "mode":
                ok, reason = self._engine.set_mode(action.mode, now)
            else:
                ok, reason = False, f"UNKNOWN_ACTION({action.kind})"

            self.action_result.emit(action.kind, ok, reason)
