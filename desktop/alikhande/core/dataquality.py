"""Is the data good enough to act on?

The scanner already refuses individual symbols for individual reasons — too few
bars, a stale tick, a spread outside its band. Those are per-pass decisions and
they are correct. What did not exist was anything that **accumulated** them,
and the difference matters for a system meant to run for years:

A symbol that fails its bar count once is a symbol whose history is still
downloading. A symbol that fails it four hundred times over two days is a
symbol the broker does not actually serve on that timeframe, and no per-pass
message will ever say so — each individual refusal is correct and forgettable,
and the pattern is the only thing that is neither.

This module holds the pattern. It grades each symbol, keeps the reasons, and
answers one question the UI could not previously ask: *which of my symbols have
been quietly unusable all week?*

## Gaps

Bar gaps are detected by spacing rather than by count. A timeframe has a known
period; consecutive bars whose times differ by more than one period have a hole
between them. Weekends produce enormous, entirely legitimate holes, so a gap is
only counted when it is **larger than one period and smaller than a weekend** —
outside that band it is either normal spacing or a market closure, and flagging
either would make the measure noise.

This deliberately under-reports. A gap hidden inside a weekend boundary is
missed. That is the right trade: a quality signal nobody trusts because it
cries wolf every Monday is worth less than one that catches the weekday holes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from .enums import Timeframe

#: A hole at least this many periods wide is treated as a market closure rather
#: than a data gap. Two days of M5 bars is a weekend; two days of D1 bars is
#: not, which is why the band is in periods rather than in seconds.
CLOSURE_PERIODS = 24


class Grade(IntEnum):
    """Ordered worst-last so ``max()`` over several timeframes is the verdict."""

    GOOD = 0
    THIN = 1  # usable, but less history than asked for
    GAPPED = 2  # holes in the series
    STALE = 3  # the series stopped advancing
    UNUSABLE = 4  # not enough to analyse at all


@dataclass
class SeriesQuality:
    """One symbol on one timeframe."""

    symbol: str = ""
    timeframe: Timeframe = Timeframe.M5
    grade: Grade = Grade.UNUSABLE
    bars_received: int = 0
    bars_required: int = 0
    gaps: int = 0
    largest_gap_periods: int = 0
    last_bar_time: int = 0
    age_seconds: int = 0
    detail: str = ""

    @property
    def usable(self) -> bool:
        return self.grade <= Grade.GAPPED


def inspect_series(
    symbol: str,
    timeframe: Timeframe,
    bar_times: list[int],
    *,
    required: int,
    now: int,
) -> SeriesQuality:
    """Grade one series from its bar timestamps alone.

    Takes times rather than bars so it can be called with whatever the caller
    already has, and so its tests do not need to construct OHLC data to check a
    spacing rule.
    """
    period = timeframe.seconds
    quality = SeriesQuality(
        symbol=symbol,
        timeframe=timeframe,
        bars_received=len(bar_times),
        bars_required=required,
    )

    if not bar_times:
        quality.grade = Grade.UNUSABLE
        quality.detail = "no bars"
        return quality

    # Good until something below demotes it. The dataclass default is UNUSABLE
    # so that a series nobody inspected can never read as fine; once inspection
    # has actually happened, the starting point is the opposite.
    quality.grade = Grade.GOOD
    quality.last_bar_time = bar_times[-1]
    quality.age_seconds = max(0, now - bar_times[-1])

    for previous, current in zip(bar_times, bar_times[1:]):
        span = current - previous
        if span <= period:
            continue
        periods = span // period
        if periods >= CLOSURE_PERIODS:
            continue  # a closure, not a hole
        quality.gaps += 1
        quality.largest_gap_periods = max(quality.largest_gap_periods, int(periods))

    if len(bar_times) < required:
        # Below half of what the analysis needs, nothing downstream will run at
        # all, so this is not "thin" — it is unusable, and saying so is what
        # lets the UI stop showing a symbol as merely warming up forever.
        if len(bar_times) * 2 < required:
            quality.grade = Grade.UNUSABLE
            quality.detail = f"{len(bar_times)} of {required} bars"
            return quality
        quality.grade = Grade.THIN
        quality.detail = f"{len(bar_times)} of {required} bars"

    # A series whose newest bar is several periods old has stopped advancing.
    # Three periods rather than one: the current bar is by definition not
    # closed, and a symbol that ticks slowly is not a broken feed.
    if quality.age_seconds > period * 3:
        quality.grade = max(quality.grade, Grade.STALE)
        quality.detail = f"newest bar is {quality.age_seconds}s old"
        return quality

    if quality.gaps:
        quality.grade = max(quality.grade, Grade.GAPPED)
        quality.detail = f"{quality.gaps} gap(s), largest {quality.largest_gap_periods} bars"

    return quality


@dataclass
class SymbolQuality:
    """The accumulated record for one symbol across every timeframe."""

    symbol: str = ""
    grade: Grade = Grade.GOOD
    series: dict[str, SeriesQuality] = field(default_factory=dict)
    #: How many passes this symbol has been graded, and how many were bad. The
    #: ratio is the number worth showing: "unusable 3 times" is noise,
    #: "unusable in 812 of 814 passes" is a verdict.
    passes: int = 0
    bad_passes: int = 0
    first_bad_at: int = 0
    last_bad_at: int = 0
    detail: str = ""

    @property
    def bad_fraction(self) -> float:
        return self.bad_passes / self.passes if self.passes else 0.0

    @property
    def chronic(self) -> bool:
        """Bad most of the time, over enough passes to mean something.

        Thirty is the same floor the evidence layer uses for a win rate, and
        for the same reason: below it the ratio is describing the sample rather
        than the symbol.
        """
        return self.passes >= 30 and self.bad_fraction >= 0.5


class DataQualityMonitor:
    """Accumulates per-pass series grades into a per-symbol record."""

    def __init__(self) -> None:
        self._symbols: dict[str, SymbolQuality] = {}

    def symbols(self) -> dict[str, SymbolQuality]:
        return dict(self._symbols)

    def get(self, symbol: str) -> SymbolQuality:
        return self._symbols.setdefault(symbol, SymbolQuality(symbol=symbol))

    def record(self, symbol: str, series: list[SeriesQuality], now: int) -> SymbolQuality:
        record = self.get(symbol)
        record.passes += 1
        for one in series:
            record.series[one.timeframe.label] = one

        record.grade = max((s.grade for s in series), default=Grade.UNUSABLE)
        if record.grade > Grade.THIN:
            record.bad_passes += 1
            record.last_bad_at = now
            if not record.first_bad_at:
                record.first_bad_at = now
            worst = max(series, key=lambda s: s.grade, default=None)
            record.detail = worst.detail if worst else ""
        else:
            record.detail = ""
        return record

    def chronic(self) -> list[SymbolQuality]:
        """Symbols that have been unusable most of the time. The Health view's
        headline, and the only output of this module that is worth interrupting
        the operator for."""
        return sorted(
            (s for s in self._symbols.values() if s.chronic),
            key=lambda s: (-s.bad_fraction, s.symbol),
        )

    def worst_grade(self) -> Grade:
        return max((s.grade for s in self._symbols.values()), default=Grade.GOOD)

    def reset(self) -> None:
        self._symbols.clear()


#: Grade to (severity, translation code), for the status chip.
_SEVERITY = {
    Grade.GOOD: ("good", "data.good"),
    Grade.THIN: ("warning", "data.thin"),
    Grade.GAPPED: ("warning", "data.gapped"),
    Grade.STALE: ("serious", "data.stale"),
    Grade.UNUSABLE: ("critical", "data.unusable"),
}


def severity_of(grade: Grade) -> tuple[str, str]:
    return _SEVERITY[grade]
