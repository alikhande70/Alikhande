"""De-duplicating event journal.

A port of ``Core/Log.mqh``'s purpose, not its implementation. A scanner that
polls every 250 ms and logs a refusal each pass produces thousands of identical
lines an hour, which is the same as producing none — nobody reads it, and the
one line that mattered is buried.

So an event is identified by ``(level, code, context)`` and repeated within
``suppress_seconds`` is counted rather than re-emitted. When it finally is
emitted again it carries the repeat count, so nothing is lost.

The journal keeps its own bounded ring of recent entries for the Health tab,
and optionally forwards to a sink (the SQLite repository, in the app) so events
survive a restart.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Iterable


class Level(IntEnum):
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3


@dataclass(frozen=True)
class Event:
    ts: int
    level: Level
    code: str
    context: str
    message: str
    repeats: int = 0

    def format(self) -> str:
        suffix = f" (x{self.repeats + 1})" if self.repeats else ""
        where = f" [{self.context}]" if self.context else ""
        return f"{self.level.name:5s}{where} {self.code}: {self.message}{suffix}"


Sink = Callable[[Event], None]


class Journal:
    def __init__(
        self,
        *,
        capacity: int = 500,
        suppress_seconds: int = 60,
        sink: Sink | None = None,
    ) -> None:
        self._entries: deque[Event] = deque(maxlen=capacity)
        self._suppress_seconds = suppress_seconds
        self._sink = sink
        # key -> (last emitted ts, suppressed count since then)
        self._seen: dict[tuple[Level, str, str], tuple[int, int]] = {}

    def set_sink(self, sink: Sink | None) -> None:
        self._sink = sink

    def entries(self) -> list[Event]:
        return list(self._entries)

    def recent(self, count: int = 50) -> list[Event]:
        return list(self._entries)[-count:]

    def errors(self) -> list[Event]:
        return [e for e in self._entries if e.level >= Level.WARN]

    def clear(self) -> None:
        self._entries.clear()
        self._seen.clear()

    def emit(self, level: Level, code: str, context: str, message: str, now: int) -> Event | None:
        """Record an event, or suppress it as a repeat.

        Returns the ``Event`` when one was actually recorded, ``None`` when it
        was folded into a running repeat count.
        """
        key = (level, code, context)
        previous = self._seen.get(key)

        if previous is not None:
            last_ts, suppressed = previous
            if now - last_ts < self._suppress_seconds:
                self._seen[key] = (last_ts, suppressed + 1)
                return None
            repeats = suppressed
        else:
            repeats = 0

        event = Event(ts=now, level=level, code=code, context=context, message=message, repeats=repeats)
        self._seen[key] = (now, 0)
        self._entries.append(event)
        if self._sink is not None:
            self._sink(event)
        return event

    def debug(self, code: str, context: str, message: str, now: int) -> Event | None:
        return self.emit(Level.DEBUG, code, context, message, now)

    def info(self, code: str, context: str, message: str, now: int) -> Event | None:
        return self.emit(Level.INFO, code, context, message, now)

    def warn(self, code: str, context: str, message: str, now: int) -> Event | None:
        return self.emit(Level.WARN, code, context, message, now)

    def error(self, code: str, context: str, message: str, now: int) -> Event | None:
        return self.emit(Level.ERROR, code, context, message, now)

    def extend(self, events: Iterable[Event]) -> None:
        """Load historical events, e.g. after a restart. Never forwarded to the
        sink — they came from it."""
        for event in events:
            self._entries.append(event)
