"""Broker connection health, and what to do about it.

The application talks to MetaTrader over local IPC. That link fails in ways an
HTTP client never does and, more importantly, it fails **quietly**: the terminal
stays open, the process stays alive, and calls keep returning — they just return
nothing. ``is_connected()`` answering ``True`` while every ``bars()`` call comes
back empty is the normal shape of a broken session, not an exotic one.

So health is not a boolean read from the gateway. It is inferred from a rolling
record of what the gateway actually did, and the states are ordered by what the
operator should do about them:

``HEALTHY``
    Probes answering, within expected latency.

``DEGRADED``
    Answering, but slowly or with intermittent failures. Scanning continues.
    This is the state that matters most, because it is the one that used to be
    invisible — a session spending four seconds per pass looks identical to a
    fast one on a screen that only shows connected/disconnected.

``STALLED``
    Answering, but the answers stopped changing. The terminal is up and the
    quotes are frozen — a weekend, a lost broker feed, or a terminal that has
    silently logged out. Distinguished from DISCONNECTED because the fix is
    different and because it is the state most likely to be mistaken for a
    quiet market.

``DISCONNECTED``
    Not answering at all.

## Why this module reconnects nothing

It decides. It does not act. ``should_reconnect`` returns a verdict and the
adapter layer carries it out, because reconnection touches process-global state
in the ``MetaTrader5`` package and must happen on the thread that owns it. A
pure decision function can be tested against a hundred failure sequences in
milliseconds; a module that reconnects can only be tested against a terminal
nobody has.

## Backoff, and why it is capped low

Exponential, capped at :data:`MAX_BACKOFF_SECONDS`. The cap is deliberately
short for a desktop application. A web client backing off to ten minutes is
being polite to someone else's server; here the "server" is a process on the
same machine that the operator may have just restarted, and making them wait
ten minutes after fixing the problem is worse than a few redundant attempts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

#: Never wait longer than this between reconnection attempts.
MAX_BACKOFF_SECONDS = 60

#: How many consecutive probe failures before the link is called disconnected.
#: Two rather than one: a single failed call during a terminal's own internal
#: reconnect is ordinary and should not repaint the whole window.
FAILURES_BEFORE_DISCONNECTED = 2

#: How long the same server time may repeat before the feed is called stalled.
#: Comfortably longer than a quiet minute on an illiquid symbol, comfortably
#: shorter than a human noticing by themselves.
STALL_SECONDS = 90


class LinkState(IntEnum):
    """Ordered by severity so ``max()`` over several probes is meaningful."""

    HEALTHY = 0
    DEGRADED = 1
    STALLED = 2
    DISCONNECTED = 3


@dataclass(frozen=True)
class Probe:
    """One observation of the link.

    ``ok`` is whether the call returned at all; ``latency_ms`` how long it took;
    ``server_time`` what the broker said the time was. The last of these is the
    only way to tell a frozen feed from a slow one — latency stays perfect when
    the terminal is happily serving a cached quote from an hour ago.
    """

    ok: bool
    latency_ms: float = 0.0
    server_time: int = 0
    detail: str = ""


@dataclass
class LinkHealth:
    """The supervisor's current verdict. Rendered directly by the Health view."""

    state: LinkState = LinkState.DISCONNECTED
    latency_ms: float = 0.0
    latency_peak_ms: float = 0.0
    consecutive_failures: int = 0
    total_failures: int = 0
    total_probes: int = 0
    last_ok_at: int = 0
    stalled_for: int = 0
    reconnect_attempts: int = 0
    next_retry_at: int = 0
    detail: str = ""

    @property
    def healthy(self) -> bool:
        return self.state == LinkState.HEALTHY

    @property
    def usable(self) -> bool:
        """May the scanner trust what this link returns?

        DEGRADED is usable — slow answers are still answers, and refusing to
        scan because a pass took 900ms would make the application useless on an
        ordinary laptop. STALLED is not: a frozen quote is worse than no quote,
        because it looks like data.
        """
        return self.state in (LinkState.HEALTHY, LinkState.DEGRADED)

    @property
    def availability(self) -> float:
        """Fraction of probes that answered, over the session."""
        if self.total_probes <= 0:
            return 0.0
        return (self.total_probes - self.total_failures) / self.total_probes


class ConnectionSupervisor:
    """Turns a stream of probes into a health verdict and a reconnect schedule.

    Holds no gateway and imports nothing. Feed it :class:`Probe` objects, read
    :attr:`health`, and ask :meth:`should_reconnect` whether now is the moment.
    """

    def __init__(
        self,
        *,
        degraded_latency_ms: float = 750.0,
        stall_seconds: int = STALL_SECONDS,
        failures_before_disconnected: int = FAILURES_BEFORE_DISCONNECTED,
    ) -> None:
        self._degraded_latency_ms = degraded_latency_ms
        self._stall_seconds = stall_seconds
        self._failures_before_disconnected = failures_before_disconnected
        self._health = LinkHealth()
        # The last *distinct* server time and when it was first seen. Tracking
        # the change rather than the value is what makes a frozen feed visible:
        # the value alone looks perfectly valid.
        self._last_server_time = 0
        self._server_time_since = 0
        self._history: list[tuple[int, LinkState]] = []

    @property
    def health(self) -> LinkHealth:
        return self._health

    def history(self) -> list[tuple[int, LinkState]]:
        """State transitions, oldest first. Only transitions are recorded — a
        link that stayed healthy for six hours is one entry, not 86,400."""
        return list(self._history)

    def observe(self, probe: Probe, now: int) -> LinkHealth:
        health = self._health
        health.total_probes += 1

        if not probe.ok:
            health.consecutive_failures += 1
            health.total_failures += 1
            health.detail = probe.detail or "probe failed"
            if health.consecutive_failures >= self._failures_before_disconnected:
                self._transition(LinkState.DISCONNECTED, now)
            else:
                # One failure is not a disconnection. Calling it DEGRADED keeps
                # it visible without repainting the window over a hiccup.
                self._transition(LinkState.DEGRADED, now)
            return health

        health.consecutive_failures = 0
        health.last_ok_at = now
        health.latency_ms = probe.latency_ms
        health.latency_peak_ms = max(health.latency_peak_ms, probe.latency_ms)
        health.reconnect_attempts = 0
        health.next_retry_at = 0

        # ---- is the feed moving? ------------------------------------------
        if probe.server_time > 0:
            if probe.server_time != self._last_server_time:
                self._last_server_time = probe.server_time
                self._server_time_since = now
                health.stalled_for = 0
            else:
                health.stalled_for = max(0, now - self._server_time_since)
        else:
            # No server time to judge by. Not an error and not evidence of
            # movement either, so the stall clock is left where it is rather
            # than being reset — resetting on a missing value would make a
            # gateway that stopped reporting time look permanently fresh.
            pass

        if health.stalled_for >= self._stall_seconds:
            health.detail = f"server time unchanged for {health.stalled_for}s"
            self._transition(LinkState.STALLED, now)
        elif probe.latency_ms >= self._degraded_latency_ms:
            health.detail = f"{probe.latency_ms:.0f}ms round trip"
            self._transition(LinkState.DEGRADED, now)
        else:
            health.detail = ""
            self._transition(LinkState.HEALTHY, now)
        return health

    def _transition(self, state: LinkState, now: int) -> None:
        if self._health.state != state:
            self._history.append((now, state))
            # Bounded. A link flapping every second for a week must not grow
            # the process without limit.
            if len(self._history) > 500:
                del self._history[:100]
        self._health.state = state

    # ------------------------------------------------------------- reconnect
    def backoff_seconds(self) -> int:
        """Delay before the next attempt: 1, 2, 4, 8 ... capped."""
        attempts = self._health.reconnect_attempts
        if attempts <= 0:
            return 0
        return min(MAX_BACKOFF_SECONDS, 2 ** (attempts - 1))

    def should_reconnect(self, now: int) -> bool:
        """Is now the moment to attempt a reconnection?

        STALLED counts. A frozen feed is often fixed by re-attaching to the
        terminal, and the alternative — waiting for a state that never changes
        by itself — is how a session spends a night serving yesterday's prices.
        """
        if self._health.state not in (LinkState.DISCONNECTED, LinkState.STALLED):
            return False
        return now >= self._health.next_retry_at

    def record_attempt(self, now: int, succeeded: bool) -> None:
        """Register the outcome of a reconnection attempt.

        On success the counters reset but the state does not: the next probe
        decides that. Declaring HEALTHY because ``initialize()`` returned true
        is how a session reports a good link while every subsequent call fails.
        """
        if succeeded:
            self._health.reconnect_attempts = 0
            self._health.next_retry_at = 0
            self._health.consecutive_failures = 0
            return
        self._health.reconnect_attempts += 1
        self._health.next_retry_at = now + self.backoff_seconds()

    def reset(self) -> None:
        """Forget everything. For a deliberate re-attach to a different account,
        where carrying the previous link's failure history forward would
        describe a session that no longer exists."""
        self._health = LinkHealth()
        self._last_server_time = 0
        self._server_time_since = 0
        self._history.clear()


@dataclass
class SupervisionSummary:
    """A flattened view for the status bar, where there is room for one line."""

    state: LinkState = LinkState.DISCONNECTED
    code: str = "LINK_DISCONNECTED"
    latency_ms: float = 0.0
    availability: float = 0.0
    detail: str = ""
    severity: str = "critical"
    fields: dict[str, str] = field(default_factory=dict)


#: State to (status-chip severity, translation code). Severity is never carried
#: by colour alone anywhere in this application, so the code travels with it.
_SEVERITY = {
    LinkState.HEALTHY: ("good", "LINK_HEALTHY"),
    LinkState.DEGRADED: ("warning", "LINK_DEGRADED"),
    LinkState.STALLED: ("serious", "LINK_STALLED"),
    LinkState.DISCONNECTED: ("critical", "LINK_DISCONNECTED"),
}


def summarise(health: LinkHealth) -> SupervisionSummary:
    severity, code = _SEVERITY[health.state]
    return SupervisionSummary(
        state=health.state,
        code=code,
        latency_ms=health.latency_ms,
        availability=health.availability,
        detail=health.detail,
        severity=severity,
        fields={
            "latency": f"{health.latency_ms:.0f} ms",
            "peak": f"{health.latency_peak_ms:.0f} ms",
            "availability": f"{health.availability * 100:.1f}%",
            "failures": str(health.total_failures),
            "probes": str(health.total_probes),
        },
    )
