"""Economic calendar gate with explicit provenance.

The trap this module exists to avoid: a naive implementation asks a calendar,
gets nothing back, and reports "no upcoming news" — which is indistinguishable
from a genuinely clear window. That is a fail-OPEN gate: silent exactly when it
cannot see. A backtest would trade straight through every NFP while appearing to
respect a news filter.

So the gate never answers "blocked or clear". It answers with a state AND a
source, and ``UNKNOWN`` is a distinct third answer that callers must handle
deliberately.

The desktop build differs from the EA in what it can reach, and the difference
is worth stating precisely. The EA could call MetaTrader's ``CalendarValueHistory``
in a live terminal. **The MetaTrader5 Python package exposes no calendar API at
all** — there is no ``calendar_*`` function in it. So a live desktop session has
*no* calendar source unless the operator supplies one.

That could have been quietly dropped. It is not, because dropping it is exactly
the fail-open failure this module was written to prevent. Instead the gate
reports ``UNKNOWN`` / ``UNAVAILABLE`` honestly, and the runtime policy decides:
in a production session UNKNOWN blocks, so a news filter that cannot see refuses
to trade rather than pretending the road is empty.

``CsvCalendar`` is the live operator adapter and requires an explicit coverage
horizon; ``StaticCalendar`` is the deterministic test/replay source. Until a
covered live source exists, the honest state is UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import NewsConfig
from .enums import NewsSource, NewsState, RuntimeKind
from .journal import Journal
from .models import NewsVerdict, RuntimeContext, currency_legs


@dataclass(frozen=True)
class CalendarEvent:
    time: int
    currency: str
    name: str
    importance: str  # HIGH | MEDIUM | LOW


class CalendarSource(Protocol):
    """A thing that can answer "what is happening between these times?".

    Deliberately tiny. Implementations may read a CSV, hit an API, or hold a
    fixed list; the gate does not care and must not.
    """

    def available(self) -> bool:
        """False when this source cannot answer right now.

        The distinction matters more than it looks: a source that is *available
        and found nothing* produces CLEAR, while a source that is *unavailable*
        produces UNKNOWN. Collapsing the two is the fail-open bug.
        """

    def events(self, since: int, until: int, currencies: tuple[str, ...]) -> list[CalendarEvent]:
        ...


class StaticCalendar:
    """A calendar backed by a supplied event list.

    Use for an operator-provided schedule, and for tests. ``available`` is True
    once events have been loaded — including when the loaded list is empty for
    the window asked about, because "I looked and there is nothing" is a real
    answer.
    """

    def __init__(self, events: list[CalendarEvent] | None = None, *, loaded: bool = False) -> None:
        self._events = list(events or [])
        self._loaded = loaded or bool(events)

    def available(self) -> bool:
        return self._loaded

    def events(self, since: int, until: int, currencies: tuple[str, ...]) -> list[CalendarEvent]:
        wanted = {c for c in currencies if c}
        return [
            event
            for event in self._events
            if since <= event.time <= until and event.currency in wanted
        ]


class CsvCalendar:
    """A live-reloadable operator-supplied calendar.

    The Python MT5 bridge has no calendar API.  A ``calendar.csv`` file is the
    smallest honest production adapter: the file's presence means a source is
    configured, every evaluation reloads it so a long-running session sees
    updates, and a malformed row raises so :class:`CalendarGate` returns
    UNKNOWN/fail-closed rather than silently skipping an event.

    Required columns are ``time,currency,name,importance,coverage_until``.
    ``time`` and ``coverage_until`` may be Unix or ISO-8601 timestamps;
    timestamps without an offset are UTC. At least one row must declare a
    coverage horizon at or beyond the requested window. A coverage-only row
    may leave the four event fields empty. This is what distinguishes an
    authoritative empty window from an old file that merely contains no future
    rows.
    """

    def __init__(self, path) -> None:
        from pathlib import Path

        self.path = Path(path)

    def available(self) -> bool:
        return self.path.is_file()

    @staticmethod
    def _timestamp(value: str) -> int:
        from datetime import datetime, timezone

        value = value.strip()
        try:
            return int(value)
        except ValueError:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return int(moment.timestamp())

    def events(self, since: int, until: int, currencies: tuple[str, ...]) -> list[CalendarEvent]:
        import csv

        wanted = {value.upper() for value in currencies if value}
        events: list[CalendarEvent] = []
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            required = {"time", "currency", "name", "importance", "coverage_until"}
            fields = {str(value).strip().lower() for value in (reader.fieldnames or [])}
            if not required.issubset(fields):
                raise ValueError(
                    "calendar.csv requires columns: "
                    "time,currency,name,importance,coverage_until"
                )
            coverage_until = 0
            for line, raw in enumerate(reader, start=2):
                row = {str(key).strip().lower(): str(value or "").strip() for key, value in raw.items()}
                if row["coverage_until"]:
                    try:
                        coverage_until = max(
                            coverage_until, self._timestamp(row["coverage_until"])
                        )
                    except ValueError as error:
                        raise ValueError(
                            f"calendar.csv line {line}: invalid coverage_until"
                        ) from error
                event_values = tuple(
                    row[name] for name in ("time", "currency", "name", "importance")
                )
                if not any(event_values):
                    continue
                if not all(event_values):
                    raise ValueError(
                        f"calendar.csv line {line}: incomplete event row"
                    )
                try:
                    event = CalendarEvent(
                        time=self._timestamp(row["time"]),
                        currency=row["currency"].upper(),
                        name=row["name"],
                        importance=row["importance"].upper(),
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(f"calendar.csv line {line}: {error}") from error
                if not event.currency or not event.name or not event.importance:
                    raise ValueError(f"calendar.csv line {line}: empty required value")
                if len(event.currency) != 3 or not event.currency.isalpha():
                    raise ValueError(f"calendar.csv line {line}: invalid currency")
                if event.importance not in {"HIGH", "MEDIUM", "LOW"}:
                    raise ValueError(f"calendar.csv line {line}: invalid importance")
                if since <= event.time <= until and (
                    not wanted or event.currency in wanted
                ):
                    events.append(event)
        if coverage_until < until:
            raise ValueError(
                f"calendar.csv coverage ends at {coverage_until}, before {until}"
            )
        return events


class CalendarGate:
    def __init__(
        self,
        source: CalendarSource | None = None,
        config: NewsConfig | None = None,
        journal: Journal | None = None,
    ) -> None:
        self._source = source
        self._config = config or NewsConfig()
        self._journal = journal or Journal()
        self._treat_unknown_as_blocking = True

    def set_source(self, source: CalendarSource | None) -> None:
        self._source = source

    def apply_runtime_policy(self, runtime: RuntimeContext, now: int) -> None:
        """How UNKNOWN resolves depends on what is at stake.

        **Production** — UNKNOWN blocks. Real orders against a calendar the
        system cannot see is exactly the situation a news filter exists to
        prevent.

        **Replay / offline** — UNKNOWN does not block, because blocking would
        mean no backtest ever produces a trade, which makes the filter's
        presence unfalsifiable rather than safe. The run proceeds NEWS-BLIND and
        must be labelled as such: its results describe a system with no news
        filter, and comparing them to a live run that has one is invalid.
        """
        self._treat_unknown_as_blocking = runtime.is_production
        if not runtime.is_production:
            self._journal.warn(
                "NEWS_BLIND_RUN",
                "",
                "no calendar in this runtime: this run applies NO news filtering "
                "and its results are not comparable to a filtered live run",
                now,
            )

    @property
    def is_news_blind(self) -> bool:
        """True when UNKNOWN is being allowed through."""
        return not self._treat_unknown_as_blocking

    def evaluate(self, symbol: str, runtime: RuntimeContext, now: int) -> NewsVerdict:
        """Evaluate the window ``[now - pre, now + post]`` on both currency legs."""
        if self._source is None or not self._source.available():
            reason = (
                "no calendar source configured; the MetaTrader5 Python API exposes none"
                if runtime.kind == RuntimeKind.LIVE
                else "no calendar source configured"
            )
            return NewsVerdict(
                state=NewsState.UNKNOWN, source=NewsSource.UNAVAILABLE, reason=reason
            )

        base, quote = currency_legs(symbol)
        since = now - self._config.pre_minutes * 60
        until = now + self._config.post_minutes * 60

        try:
            events = self._source.events(since, until, (base, quote))
        except Exception as error:
            self._journal.warn(
                "CALENDAR_UNAVAILABLE", symbol, f"calendar query failed: {error}", now
            )
            return NewsVerdict(
                state=NewsState.UNKNOWN,
                source=NewsSource.UNAVAILABLE,
                reason="calendar query failed",
            )

        wanted = {"HIGH"}
        if self._config.include_medium_importance:
            wanted.add("MEDIUM")

        for event in events:
            if event.importance.upper() not in wanted:
                continue
            return NewsVerdict(
                state=NewsState.BLOCKED,
                source=NewsSource.LIVE,
                event_name=event.name,
                currency=event.currency,
                event_time=event.time,
                reason=f"{event.currency} {event.name}",
            )

        return NewsVerdict(state=NewsState.CLEAR, source=NewsSource.LIVE, reason="window clear")

    def blocks_trading(self, verdict: NewsVerdict) -> bool:
        """The only place the tri-state collapses to a decision.

        Kept separate from ``evaluate`` so the UI can always show the true state
        even when the trading decision has to be binary.
        """
        if verdict.state == NewsState.BLOCKED:
            return True
        if verdict.state == NewsState.UNKNOWN:
            return self._treat_unknown_as_blocking
        return False
