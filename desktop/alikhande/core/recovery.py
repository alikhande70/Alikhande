"""What survived the last shutdown, and whether it was a shutdown at all.

The execution layer already recovers the thing that matters most: an unresolved
order keeps the submit gate shut across a restart, because the record is
persisted before the send and re-read on launch. That is untouched.

What did not exist was any notion of a **session**. The application had no idea
whether it had been closed deliberately, killed by the operator, or lost to a
power cut, and those three want different things on the next launch:

- A clean exit needs nothing. Restore the last view and carry on.
- A crash needs the operator told, plainly, that the previous session ended
  without closing — and needs the diagnostics from it kept rather than
  overwritten by the new session's.
- A crash **while an order was in flight** is the case the whole safety
  apparatus exists for, and it must be the first thing on screen.

## How a crash is detected

By absence, not by presence. A session writes a record on start with
``closed_at = 0``, and sets it on the way out. A record still holding zero when
a later session reads it means nobody ran the shutdown path. There is no
heartbeat and no timestamp comparison, because both introduce a window where a
slow machine is mistaken for a dead one.

The cost of this design is that a session killed with the file on a read-only
volume looks clean. That is acceptable: the failure mode is under-reporting a
crash, and the execution gate — which does not depend on any of this — is what
actually protects the account.

## Why the previous session is kept rather than replaced

A crash's evidence is written by the session that crashed, and the natural
instinct is to overwrite it at the next start. Doing so destroys the only
record of the thing the operator most needs to look at. Sessions are kept in a
bounded ring instead, newest last.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import IntEnum

#: How many past sessions to keep. Enough to cover a bad week without letting
#: the file grow forever.
SESSION_HISTORY = 50


class ExitKind(IntEnum):
    CLEAN = 0  # the shutdown path ran
    CRASH = 1  # it did not
    RUNNING = 2  # this is the current session
    UNKNOWN = 3  # no record at all — a first launch, or a wiped data directory


@dataclass(frozen=True)
class SessionRecord:
    """One run of the application, start to finish."""

    session_id: str = ""
    environment: str = ""
    version: str = ""
    started_at: int = 0
    closed_at: int = 0
    #: The last view the operator was on. Restored on a clean start.
    last_view: str = ""
    #: Was an execution unresolved when this session ended? Persisted here as
    #: well as in the execution table, deliberately: this is the flag the
    #: launch banner reads, and it must not depend on the database that the
    #: crash may have left mid-write.
    execution_in_flight: bool = False
    in_flight_symbol: str = ""
    #: Free-form counters kept for the diagnostics bundle.
    stats: dict[str, str] = field(default_factory=dict)

    @property
    def exit_kind(self) -> ExitKind:
        return ExitKind.CLEAN if self.closed_at else ExitKind.CRASH

    @property
    def duration(self) -> int:
        if not self.closed_at:
            return 0
        return max(0, self.closed_at - self.started_at)


@dataclass(frozen=True)
class RecoveryVerdict:
    """What the launch banner should say, and how loudly.

    ``severity`` is one of ``good`` / ``warning`` / ``serious`` / ``critical``
    and travels with ``code`` so colour never carries the message alone.
    """

    kind: ExitKind = ExitKind.UNKNOWN
    severity: str = "good"
    code: str = "RECOVERY_FIRST_RUN"
    previous: SessionRecord | None = None
    #: True when the operator must be shown this before anything else.
    interrupt: bool = False
    detail: str = ""

    @property
    def quiet(self) -> bool:
        return not self.interrupt and self.severity == "good"


def assess(previous: SessionRecord | None) -> RecoveryVerdict:
    """Classify the previous session.

    The ordering here is the whole point. An unresolved execution outranks a
    plain crash, because "the app died" and "the app died holding an order the
    broker may or may not have filled" are not the same news and must not
    render as the same banner.
    """
    if previous is None:
        return RecoveryVerdict(
            kind=ExitKind.UNKNOWN,
            severity="good",
            code="RECOVERY_FIRST_RUN",
            interrupt=False,
        )

    if previous.exit_kind == ExitKind.CLEAN:
        if previous.execution_in_flight:
            # A clean exit that still recorded an in-flight order. Rare and
            # serious: the operator closed the window on an unresolved
            # execution, which the submit gate will have kept shut, and they
            # need to know why nothing will send until they clear it.
            return RecoveryVerdict(
                kind=ExitKind.CLEAN,
                severity="serious",
                code="RECOVERY_CLEAN_WITH_UNRESOLVED",
                previous=previous,
                interrupt=True,
                detail=previous.in_flight_symbol,
            )
        return RecoveryVerdict(
            kind=ExitKind.CLEAN,
            severity="good",
            code="RECOVERY_CLEAN",
            previous=previous,
            interrupt=False,
        )

    if previous.execution_in_flight:
        return RecoveryVerdict(
            kind=ExitKind.CRASH,
            severity="critical",
            code="RECOVERY_CRASH_WITH_UNRESOLVED",
            previous=previous,
            interrupt=True,
            detail=previous.in_flight_symbol,
        )

    return RecoveryVerdict(
        kind=ExitKind.CRASH,
        severity="warning",
        code="RECOVERY_CRASH",
        previous=previous,
        interrupt=True,
    )


class SessionLedger:
    """The ring of past sessions, and the current one.

    Storage-agnostic: it holds records and hands them to a writer. The writer
    is a JSON file in the app, and a list in tests, which is what lets crash
    recovery be tested without killing a process.
    """

    def __init__(self, history: list[SessionRecord] | None = None) -> None:
        self._history: list[SessionRecord] = list(history or [])
        self._current: SessionRecord | None = None

    def history(self) -> list[SessionRecord]:
        return list(self._history)

    @property
    def current(self) -> SessionRecord | None:
        return self._current

    def previous(self) -> SessionRecord | None:
        """The most recent session that is not this one."""
        return self._history[-1] if self._history else None

    def open(self, record: SessionRecord) -> RecoveryVerdict:
        """Start a session. Returns the verdict on the one before it.

        The verdict is computed *before* the new record is appended, so a
        launch cannot assess itself — which it would otherwise do, always
        finding a session with ``closed_at == 0`` and reporting a crash on
        every single start.
        """
        verdict = assess(self.previous())
        self._current = replace(record, closed_at=0)
        self._history.append(self._current)
        if len(self._history) > SESSION_HISTORY:
            del self._history[: len(self._history) - SESSION_HISTORY]
        return verdict

    def mark_in_flight(self, symbol: str, in_flight: bool) -> None:
        """Record that an execution is (or is no longer) unresolved.

        Called from the scan loop rather than only at shutdown, because the
        entire value of the flag is being correct at the moment the process
        dies — and a process that dies does not run its shutdown path.
        """
        if self._current is None:
            return
        self._current = replace(
            self._current,
            execution_in_flight=in_flight,
            in_flight_symbol=symbol if in_flight else "",
        )
        self._history[-1] = self._current

    def update_view(self, view: str) -> None:
        if self._current is None:
            return
        self._current = replace(self._current, last_view=view)
        self._history[-1] = self._current

    def close(self, now: int, stats: dict[str, str] | None = None) -> SessionRecord | None:
        """Run the shutdown path. Its *absence* is what marks a crash."""
        if self._current is None:
            return None
        self._current = replace(
            self._current, closed_at=max(now, self._current.started_at), stats=stats or {}
        )
        self._history[-1] = self._current
        closed = self._current
        self._current = None
        return closed

    # ------------------------------------------------------------ statistics
    def crash_count(self) -> int:
        return sum(1 for s in self._history if s.closed_at == 0 and s is not self._current)

    def uptime_total(self) -> int:
        return sum(s.duration for s in self._history)
