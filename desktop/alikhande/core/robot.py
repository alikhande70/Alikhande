"""The robot: everything a person should not have to do by hand, and nothing more.

The goal is that a normal day never requires opening MetaTrader, and rarely
requires touching this application either. The robot watches sessions, rotates
symbols, keeps the link alive, takes backups, escalates health, pauses itself
when the account says stop, and queues qualified candidates with their evidence
already assembled.

## What it deliberately does not do, and why

It does not arm and it does not confirm.

This is the one design decision in the module and it is worth stating plainly,
because "complete the automation" reads as "let it trade on its own" and that
would dismantle the gate the whole project is built around. Execution requires
**two deliberate human actions on separate controls** inside a short TTL. An
autopilot that armed automatically would not preserve that gate in weakened
form — it would remove it, because a single Confirm click would then be
sufficient to send an order. Two actions where the robot performs one is one
action.

So the robot's job stops exactly where judgement starts. It does everything
that makes the two remaining clicks fast and well-informed, which is most of
the work and all of the tedium.

The reverse direction is unrestricted. The robot may **disarm**, cancel, pause
and stop entirely on its own, without asking, at any time. Actions that reduce
exposure need no ceremony; only actions that create it do.

:data:`AUTO_EXECUTE_LOCK` follows the production-send pattern: the capability is
named, its consequences are modelled, the plumbing that would report it exists,
and it is locked closed with no setter. When and if unattended execution is ever
authorised it arrives as its own reviewed change.

## Windows are in broker server time

Never local time. A session window is a statement about the market, and the
market does not know what timezone the operator's laptop is in. Every ``now``
the robot sees comes from the gateway's ``server_time``, which is the same clock
the signal TTLs, arming expiry and news windows already use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from .environment import capabilities

#: Unattended execution. Locked, and there is no code that opens it.
AUTO_EXECUTE_LOCK = "AUTO_EXECUTE_NOT_AUTHORISED"

#: Seconds. A robot that has paused itself re-evaluates this often rather than
#: staying paused until somebody notices.
PAUSE_REVIEW_SECONDS = 300


class RobotState(IntEnum):
    """Ordered by how much the robot is currently doing."""

    STOPPED = 0  # switched off by the operator
    IDLE = 1  # on, but outside every session window
    WATCHING = 2  # on, in a window, scanning
    HOLDING = 3  # in a window, but something says do not act
    PAUSED = 4  # paused itself; will re-evaluate


class HoldReason(IntEnum):
    """Why the robot is not presenting candidates. Ordered by severity."""

    NONE = 0
    OUTSIDE_WINDOW = 1
    LINK_UNUSABLE = 2
    DATA_UNUSABLE = 3
    NEWS_BLOCKED = 4
    RISK_GUARD = 5
    EXECUTION_UNRESOLVED = 6
    ENVIRONMENT_LOCKED = 7


@dataclass(frozen=True)
class SessionWindow:
    """One trading window, in broker server time.

    ``start_minute`` and ``end_minute`` are minutes past midnight so a window
    can be compared without constructing a datetime, and so a window that wraps
    midnight (Asia) is expressible as ``start > end`` rather than as two rows
    the operator has to keep in sync.
    """

    name: str
    start_minute: int
    end_minute: int
    #: Monday is 0, matching ``datetime.weekday()``. Empty means every day.
    days: tuple[int, ...] = ()
    enabled: bool = True

    def contains(self, weekday: int, minute_of_day: int) -> bool:
        if not self.enabled:
            return False
        if self.days and weekday not in self.days:
            return False
        if self.start_minute <= self.end_minute:
            return self.start_minute <= minute_of_day < self.end_minute
        # Wraps midnight. The day check above applies to the *start* day, which
        # is what an operator means by "the Asian session on Tuesday".
        return minute_of_day >= self.start_minute or minute_of_day < self.end_minute


#: Sensible defaults, in broker server time, weekdays only. Named rather than
#: numbered so the Robot view can show what they are without a legend.
DEFAULT_WINDOWS: tuple[SessionWindow, ...] = (
    SessionWindow("london", 7 * 60, 16 * 60, days=(0, 1, 2, 3, 4)),
    SessionWindow("newyork", 12 * 60, 21 * 60, days=(0, 1, 2, 3, 4)),
    SessionWindow("asia", 23 * 60, 8 * 60, days=(0, 1, 2, 3, 6), enabled=False),
)


@dataclass
class RobotPolicy:
    """What the operator has allowed the robot to do.

    Every field defaults to the conservative answer. A robot enabled with no
    configuration watches, notifies and maintains — it never widens anything.
    """

    enabled: bool = False
    windows: tuple[SessionWindow, ...] = DEFAULT_WINDOWS

    # ---- what it may do on its own ---------------------------------------
    #: Reconnect a dropped or stalled link.
    auto_reconnect: bool = True
    #: Disarm a stale armed intent, and cancel when structure invalidates.
    #: Reducing exposure needs no ceremony.
    auto_disarm: bool = True
    #: Pause itself when a risk guard trips.
    auto_pause_on_guard: bool = True
    #: Pause itself when data or the link go unusable.
    auto_pause_on_degradation: bool = True
    #: Take a verified backup on the schedule below.
    auto_backup: bool = True
    backup_interval_hours: int = 12

    # ---- what it may never do --------------------------------------------
    #: Present here so the UI can show the capability and its lock, and so a
    #: reader of this dataclass sees the whole surface rather than wondering
    #: what was left out. Setting it True changes nothing: `may_execute()`
    #: never consults it.
    auto_execute_requested: bool = False

    #: Only surface candidates at or above this rule score. Not a new gate —
    #: the scoring threshold still applies underneath — but an operator who
    #: only wants to be interrupted for the best setups should not have to
    #: raise the global threshold to get that.
    minimum_score: float = 0.0

    def may_execute(self) -> tuple[bool, str]:
        """Always ``(False, AUTO_EXECUTE_LOCK)``.

        Written as a method returning the lock rather than as a missing feature
        so that every caller has somewhere to ask, and so the answer is a
        reason code the UI can explain rather than an absence it has to guess
        the meaning of.
        """
        return False, AUTO_EXECUTE_LOCK


@dataclass
class RobotStatus:
    """What the robot is doing, for the Robot view and the status bar."""

    state: RobotState = RobotState.STOPPED
    hold: HoldReason = HoldReason.NONE
    window: str = ""
    next_window: str = ""
    next_window_in: int = 0
    candidates: int = 0
    paused_until: int = 0
    last_backup_at: int = 0
    #: Codes for everything the robot did this pass. Rendered as a live feed,
    #: which is the only way an unattended system is believable — a robot that
    #: shows nothing while claiming to work is indistinguishable from one that
    #: has silently stopped.
    actions: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def active(self) -> bool:
        return self.state == RobotState.WATCHING

    @property
    def severity(self) -> str:
        if self.state == RobotState.STOPPED:
            return "unknown"
        if self.state == RobotState.PAUSED:
            return "serious"
        if self.state == RobotState.HOLDING:
            return "warning"
        return "good"


@dataclass(frozen=True)
class RobotDecision:
    """One pass's worth of instructions for the app layer to carry out.

    The robot decides; the app acts. Same split as the connection supervisor,
    and for the same reason: every one of these can be asserted against in a
    test without a terminal, a database or a window.
    """

    reconnect: bool = False
    disarm: bool = False
    backup: bool = False
    notify: tuple[tuple[str, str], ...] = ()  # (subject, detail)
    status: RobotStatus = field(default_factory=RobotStatus)


class Robot:
    """Decides, each pass, what the automation layer should do."""

    def __init__(self, policy: RobotPolicy | None = None) -> None:
        self._policy = policy or RobotPolicy()
        self._status = RobotStatus()
        self._paused_until = 0
        self._last_backup_at = 0
        self._previous_state = RobotState.STOPPED

    @property
    def policy(self) -> RobotPolicy:
        return self._policy

    @property
    def status(self) -> RobotStatus:
        return self._status

    def configure(self, policy: RobotPolicy) -> None:
        self._policy = policy

    def stop(self) -> None:
        self._paused_until = 0
        self._status = RobotStatus(state=RobotState.STOPPED)

    def resume(self) -> None:
        """Clear a self-imposed pause. The operator's override of the robot's
        own caution, which they are entitled to — the underlying gates are all
        still in place regardless of what the robot thinks."""
        self._paused_until = 0

    # ------------------------------------------------------------- windowing
    def active_window(self, weekday: int, minute_of_day: int) -> SessionWindow | None:
        for window in self._policy.windows:
            if window.contains(weekday, minute_of_day):
                return window
        return None

    def next_window(self, weekday: int, minute_of_day: int) -> tuple[str, int]:
        """The next window to open, and how many minutes away it is.

        Scans forward a week in minutes rather than solving it arithmetically.
        Ten thousand iterations of an integer comparison once per pass is
        nothing, and the arithmetic version has to special-case midnight wrap,
        disabled windows and day filters — three places to get it subtly wrong
        in exchange for microseconds nobody will ever measure.
        """
        enabled = [w for w in self._policy.windows if w.enabled]
        if not enabled:
            return "", 0
        for ahead in range(1, 7 * 24 * 60 + 1):
            minute = (minute_of_day + ahead) % (24 * 60)
            day = (weekday + (minute_of_day + ahead) // (24 * 60)) % 7
            for window in enabled:
                if window.contains(day, minute):
                    return window.name, ahead
        return "", 0

    # ---------------------------------------------------------------- decide
    def evaluate(
        self,
        *,
        now: int,
        weekday: int,
        minute_of_day: int,
        environment: str,
        link_usable: bool,
        data_usable: bool,
        news_blocked: bool,
        may_trade: bool,
        execution_unresolved: bool,
        candidates: int,
        armed_stale: bool = False,
    ) -> RobotDecision:
        """One pass. Returns what the app should do and the status to display."""
        status = RobotStatus()
        actions: list[str] = []
        notify: list[tuple[str, str]] = []

        if not self._policy.enabled:
            self._status = RobotStatus(state=RobotState.STOPPED)
            self._previous_state = RobotState.STOPPED
            return RobotDecision(status=self._status)

        # ---- maintenance runs regardless of window ------------------------
        # A backup is not a trading action. Tying it to a session window means
        # a machine that only ever runs overnight never gets one.
        backup = False
        if self._policy.auto_backup:
            interval = max(1, self._policy.backup_interval_hours) * 3600
            if now - self._last_backup_at >= interval:
                backup = True
                self._last_backup_at = now
                actions.append("BACKUP")
        status.last_backup_at = self._last_backup_at

        # Reconnection is likewise not a trading action, and a link that is
        # down outside a window must be back up before the next one opens.
        reconnect = self._policy.auto_reconnect and not link_usable
        if reconnect:
            actions.append("RECONNECT")

        # Disarming reduces exposure, so it never waits for anything.
        disarm = self._policy.auto_disarm and armed_stale
        if disarm:
            actions.append("DISARM")

        # ---- am I paused? --------------------------------------------------
        if self._paused_until and now < self._paused_until:
            status.state = RobotState.PAUSED
            status.paused_until = self._paused_until
            status.detail = "paused"
            status.actions = actions
            self._status = status
            return RobotDecision(
                reconnect=reconnect, disarm=disarm, backup=backup, status=status
            )
        if self._paused_until:
            self._paused_until = 0
            actions.append("PAUSE_EXPIRED")

        # ---- in a window? --------------------------------------------------
        window = self.active_window(weekday, minute_of_day)
        name, minutes = self.next_window(weekday, minute_of_day)
        status.next_window = name
        status.next_window_in = minutes

        if window is None:
            status.state = RobotState.IDLE
            status.hold = HoldReason.OUTSIDE_WINDOW
            status.actions = actions
            self._status = status
            self._previous_state = RobotState.IDLE
            return RobotDecision(
                reconnect=reconnect, disarm=disarm, backup=backup, status=status
            )

        status.window = window.name

        # ---- anything saying do not act? -----------------------------------
        # Ordered by severity so the *worst* reason is the one displayed. An
        # operator told "outside window" while a risk guard is tripped has been
        # told the least useful true thing available.
        hold = HoldReason.NONE
        caps = capabilities(environment)
        if execution_unresolved:
            hold = HoldReason.EXECUTION_UNRESOLVED
        elif not may_trade:
            hold = HoldReason.RISK_GUARD
        elif news_blocked and caps.news_unknown_blocks:
            hold = HoldReason.NEWS_BLOCKED
        elif not data_usable:
            hold = HoldReason.DATA_UNUSABLE
        elif not link_usable:
            hold = HoldReason.LINK_UNUSABLE

        if hold != HoldReason.NONE:
            status.state = RobotState.HOLDING
            status.hold = hold
            status.detail = hold.name

            should_pause = (
                self._policy.auto_pause_on_guard
                and hold in (HoldReason.RISK_GUARD, HoldReason.EXECUTION_UNRESOLVED)
            ) or (
                self._policy.auto_pause_on_degradation
                and hold in (HoldReason.LINK_UNUSABLE, HoldReason.DATA_UNUSABLE)
            )
            if should_pause:
                self._paused_until = now + PAUSE_REVIEW_SECONDS
                status.state = RobotState.PAUSED
                status.paused_until = self._paused_until
                actions.append("PAUSE")
                if self._previous_state != RobotState.PAUSED:
                    notify.append(("robot.paused", hold.name))

            status.actions = actions
            self._status = status
            self._previous_state = status.state
            return RobotDecision(
                reconnect=reconnect,
                disarm=disarm,
                backup=backup,
                notify=tuple(notify),
                status=status,
            )

        # ---- watching -------------------------------------------------------
        status.state = RobotState.WATCHING
        status.candidates = candidates
        if self._previous_state in (RobotState.PAUSED, RobotState.HOLDING):
            notify.append(("robot.resumed", window.name))
        if candidates:
            actions.append("PRESENT")

        status.actions = actions
        self._status = status
        self._previous_state = RobotState.WATCHING
        return RobotDecision(
            reconnect=reconnect,
            disarm=disarm,
            backup=backup,
            notify=tuple(notify),
            status=status,
        )


def minute_of_day(timestamp: int) -> tuple[int, int]:
    """``(weekday, minutes past midnight)`` for a broker server timestamp.

    UTC, because the timestamp is the broker's own clock already converted by
    the gateway. Applying a local timezone here would shift every window by
    whatever the operator's machine happens to be set to, which is the exact
    bug this function exists to avoid.
    """
    from datetime import datetime, timezone

    moment = datetime.fromtimestamp(timestamp, timezone.utc)
    return moment.weekday(), moment.hour * 60 + moment.minute
