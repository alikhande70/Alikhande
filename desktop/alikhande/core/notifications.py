"""What is worth interrupting the operator for, and how often.

An application that runs for months unattended has exactly one way to fail the
person using it: telling them everything, or telling them nothing. This module
is the policy that sits between.

## Routing is by consequence, not by log level

A journal entry answers "what happened". A notification answers "does somebody
need to look at this now", and the two are not the same question — most ERROR
entries do not need a human tonight, and one INFO event (an unresolved
execution clearing) very much does. So notifications carry their own
:class:`Urgency`, assigned by what the event *means*, and the mapping lives
here rather than being inherited from the journal's severity.

## Delivery is throttled per subject, not globally

A global rate limit is the wrong shape. It lets a chatty subject crowd out a
quiet, important one — forty spread warnings will suppress the single
disconnection notice that arrived behind them. Throttling per subject means
each distinct thing gets its own budget and a burst of one cannot silence
another.

The exception is :attr:`Urgency.CRITICAL`, which is never throttled. If the
same critical condition fires forty times, the operator should see forty; the
alternative is an application that decides on its own that a repeated emergency
has become background noise.

## Channels are declarative and the router does not own any of them

:class:`Notification` says what happened and how urgent it is. Whether that
becomes a toast, a sound, a row in a panel or a line in a file is the app
layer's business. Keeping delivery out of here is what lets the whole policy be
tested without a desktop session — which is the only way it will ever be tested
against the sequences that matter, like six hours of intermittent disconnects.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Iterable


class Urgency(IntEnum):
    """Ordered. ``>=`` comparisons against a threshold are the point."""

    INFO = 0  # worth a line in the panel; never interrupts
    NOTABLE = 1  # a signal appeared, an order filled
    WARNING = 2  # degraded, but running
    CRITICAL = 3  # stopped, or unsafe — never throttled


class Channel(IntEnum):
    """Where a notification may go. A notification names the channels it is
    *eligible* for; the app decides which of those actually exist."""

    PANEL = 0  # the in-app notification list — always available
    TOAST = 1  # a desktop notification
    SOUND = 2
    FILE = 3  # appended to a log the operator can tail


@dataclass(frozen=True)
class Notification:
    ts: int
    urgency: Urgency
    #: Groups related events for throttling. Two disconnections are the same
    #: subject; a disconnection and a spread warning are not.
    subject: str
    #: Translation key for the headline.
    title_key: str
    #: Already-formatted detail. Not a key: it carries numbers and symbol names
    #: that would need a template per combination.
    detail: str = ""
    symbol: str = ""
    channels: tuple[Channel, ...] = (Channel.PANEL,)
    #: How many identical notifications were folded into this one.
    suppressed: int = 0

    @property
    def interrupts(self) -> bool:
        return self.urgency >= Urgency.WARNING


#: Subject to the urgency it is delivered at. Everything the application can
#: notify about is listed here, so adding a notification means making a
#: deliberate decision about whether it is allowed to interrupt somebody.
SUBJECTS: dict[str, Urgency] = {
    # ---- the link -----------------------------------------------------------
    "link.disconnected": Urgency.CRITICAL,
    "link.stalled": Urgency.CRITICAL,
    "link.degraded": Urgency.WARNING,
    "link.restored": Urgency.NOTABLE,
    # ---- execution ----------------------------------------------------------
    "execution.unresolved": Urgency.CRITICAL,
    "execution.resolved": Urgency.NOTABLE,
    "execution.rejected": Urgency.WARNING,
    "execution.filled": Urgency.NOTABLE,
    "execution.defect": Urgency.CRITICAL,
    # ---- risk ---------------------------------------------------------------
    "risk.guard_tripped": Urgency.CRITICAL,
    "risk.daily_limit": Urgency.CRITICAL,
    "risk.exposure_high": Urgency.WARNING,
    # ---- the scanner --------------------------------------------------------
    "signal.confirmed": Urgency.NOTABLE,
    "signal.expired": Urgency.INFO,
    # ---- data ---------------------------------------------------------------
    "data.chronic": Urgency.WARNING,
    "data.stale": Urgency.WARNING,
    # ---- lifecycle ----------------------------------------------------------
    "session.crash_recovered": Urgency.CRITICAL,
    "session.started": Urgency.INFO,
    "backup.failed": Urgency.WARNING,
    "backup.written": Urgency.INFO,
    "robot.paused": Urgency.WARNING,
    "robot.resumed": Urgency.NOTABLE,
    "robot.window_closed": Urgency.INFO,
}

#: Default throttle per subject, in seconds. A subject not listed uses
#: :data:`DEFAULT_THROTTLE`.
THROTTLE: dict[str, int] = {
    "link.degraded": 300,
    "data.stale": 600,
    "data.chronic": 3600,
    "risk.exposure_high": 300,
    "signal.expired": 900,
}

DEFAULT_THROTTLE = 60


Delivery = Callable[[Notification], None]


class NotificationRouter:
    """Applies the policy and hands survivors to a delivery callable."""

    def __init__(
        self,
        *,
        minimum_urgency: Urgency = Urgency.INFO,
        capacity: int = 200,
        delivery: Delivery | None = None,
    ) -> None:
        self._minimum = minimum_urgency
        self._recent: deque[Notification] = deque(maxlen=capacity)
        self._delivery = delivery
        #: subject -> (last delivered ts, suppressed since)
        self._last: dict[str, tuple[int, int]] = {}
        self._unread = 0

    # ------------------------------------------------------------- accessors
    def recent(self, count: int = 50) -> list[Notification]:
        return list(self._recent)[-count:]

    def all(self) -> list[Notification]:
        return list(self._recent)

    @property
    def unread(self) -> int:
        return self._unread

    def mark_read(self) -> None:
        self._unread = 0

    def set_delivery(self, delivery: Delivery | None) -> None:
        self._delivery = delivery

    def set_minimum_urgency(self, urgency: Urgency) -> None:
        self._minimum = urgency

    def clear(self) -> None:
        self._recent.clear()
        self._last.clear()
        self._unread = 0

    # ---------------------------------------------------------------- notify
    def notify(
        self,
        subject: str,
        detail: str = "",
        *,
        now: int,
        symbol: str = "",
        urgency: Urgency | None = None,
        channels: Iterable[Channel] | None = None,
    ) -> Notification | None:
        """Raise a notification, or fold it into a running suppression count.

        Returns the delivered :class:`Notification`, or ``None`` when it was
        throttled or fell below the minimum urgency. Returning ``None`` rather
        than a suppressed object keeps callers from accidentally treating a
        swallowed event as a delivered one.
        """
        level = urgency if urgency is not None else SUBJECTS.get(subject, Urgency.INFO)
        if level < self._minimum:
            return None

        suppressed = 0
        if level < Urgency.CRITICAL:
            # Critical is never throttled: an application that decides a
            # repeated emergency has become background noise is worse than one
            # that repeats itself.
            window = THROTTLE.get(subject, DEFAULT_THROTTLE)
            previous = self._last.get(subject)
            if previous is not None:
                last_ts, held = previous
                if now - last_ts < window:
                    self._last[subject] = (last_ts, held + 1)
                    return None
                suppressed = held

        notification = Notification(
            ts=now,
            urgency=level,
            subject=subject,
            title_key=f"notify.{subject}",
            detail=detail,
            symbol=symbol,
            channels=tuple(channels) if channels else _channels_for(level),
            suppressed=suppressed,
        )
        self._last[subject] = (now, 0)
        self._recent.append(notification)
        self._unread += 1
        if self._delivery is not None:
            self._delivery(notification)
        return notification

    # ------------------------------------------------------------- summaries
    def counts(self) -> dict[Urgency, int]:
        tally: dict[Urgency, int] = {u: 0 for u in Urgency}
        for item in self._recent:
            tally[item.urgency] += 1
        return tally

    def worst(self) -> Urgency | None:
        """The highest urgency currently held, or ``None`` when empty."""
        if not self._recent:
            return None
        return max(item.urgency for item in self._recent)


def _channels_for(urgency: Urgency) -> tuple[Channel, ...]:
    """Which channels an urgency is eligible for.

    Escalating rather than exclusive: everything lands in the panel, and higher
    urgencies add channels rather than moving between them. A critical event
    that only made a sound and left no row is one the operator cannot go back
    and read.
    """
    if urgency >= Urgency.CRITICAL:
        return (Channel.PANEL, Channel.TOAST, Channel.SOUND, Channel.FILE)
    if urgency >= Urgency.WARNING:
        return (Channel.PANEL, Channel.TOAST, Channel.FILE)
    if urgency >= Urgency.NOTABLE:
        return (Channel.PANEL, Channel.FILE)
    return (Channel.PANEL,)


@dataclass
class NotificationSettings:
    """Operator-facing preferences. Stored, so keep it plain."""

    enabled: bool = True
    minimum_urgency: Urgency = Urgency.NOTABLE
    toasts: bool = True
    sounds: bool = False
    #: Subjects the operator has explicitly muted. Critical subjects are
    #: honoured here too — muting is a deliberate act and the application
    #: should not overrule it — but the UI marks them so the choice is visible
    #: rather than forgotten.
    muted: set[str] = field(default_factory=set)

    def allows(self, notification: Notification) -> bool:
        if not self.enabled:
            return False
        if notification.subject in self.muted:
            return False
        return notification.urgency >= self.minimum_urgency

    def channels_for(self, notification: Notification) -> tuple[Channel, ...]:
        allowed = []
        for channel in notification.channels:
            if channel == Channel.TOAST and not self.toasts:
                continue
            if channel == Channel.SOUND and not self.sounds:
                continue
            allowed.append(channel)
        return tuple(allowed)
