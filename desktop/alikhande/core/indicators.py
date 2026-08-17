"""Indicators, computed in-process from OHLC bars.

This is the largest single departure from the MQL5 build, and it is a
deliberate upgrade rather than a translation.

The EA obtained EMA / ADX / ATR through MetaTrader indicator handles and
``CopyBuffer``. That carries three problems the desktop build simply does not
have:

* ``BarsCalculated`` is unreliable immediately after a handle is created, so
  the first reads after startup can silently return nothing.
* Handles are a leaky terminal-global resource, which is why the EA needed a
  whole caching module to avoid exhausting them.
* Nothing about the calculation could be tested without a terminal.

Computing them here removes all three: the functions below are pure, take a
list of bars, and are covered by unit tests that actually run.

What it costs, stated plainly: these values are no longer guaranteed identical
to MetaTrader's built-in indicators. The formulas below follow MetaTrader 5's
published indicator sources, including the detail that **MT5's ATR is a simple
moving average of True Range**, not the Wilder smoothing MT4 used. That
agreement is *asserted from the documented algorithm, not measured against a
terminal* — see docs/VERIFICATION.md. This is why the desktop build carries its
own ``RULE_VERSION`` suffix: its outcomes are never pooled with the EA's.

Conventions, chosen once so no call site has to think about it:

* Input bars are **chronological** — ``bars[0]`` is oldest, ``bars[-1]`` is the
  most recent. This is the opposite of MQL5's series indexing, and it is the
  natural order for every algorithm below.
* Output series are the same length as the input, with ``None`` for every bar
  where the indicator has not yet warmed up. Returning ``None`` rather than
  ``0.0`` means an unwarmed value can never be mistaken for a real reading —
  the same reasoning behind the tri-state news gate.
"""

from __future__ import annotations

from .models import Bar

Series = list[float | None]


def closes(bars: list[Bar]) -> list[float]:
    return [b.close for b in bars]


def ema(values: list[float], period: int) -> Series:
    """Exponential moving average.

    Seeded with the first value, then ``ema[i] = v[i]*k + ema[i-1]*(1-k)`` with
    ``k = 2/(period+1)``. This matches MetaTrader's ``ExponentialMAOnBuffer``,
    which seeds from the first price rather than from an SMA — a difference
    that matters for the first few hundred bars and then decays away.
    """
    if period < 1 or not values:
        return [None] * len(values)

    k = 2.0 / (period + 1.0)
    out: Series = [None] * len(values)
    current = values[0]
    out[0] = current
    for i in range(1, len(values)):
        current = values[i] * k + current * (1.0 - k)
        out[i] = current
    return out


def true_range(bars: list[Bar]) -> Series:
    """True Range. Undefined for the first bar, which has no previous close."""
    out: Series = [None] * len(bars)
    for i in range(1, len(bars)):
        previous_close = bars[i - 1].close
        out[i] = max(bars[i].high, previous_close) - min(bars[i].low, previous_close)
    return out


def atr(bars: list[Bar], period: int = 14) -> Series:
    """Average True Range, as MetaTrader 5 computes it.

    MT5's built-in ATR averages True Range with a **simple** moving average.
    Its published source advances the value with
    ``atr[i] = atr[i-1] + (tr[i] - tr[i-period]) / period``, which is exactly a
    rolling SMA update. MT4 (and Wilder's original) used a smoothed average
    instead; the two diverge materially, so this is not a detail to guess at.

    The first defined value lands at index ``period`` — one bar later than a
    naive implementation, because True Range itself is undefined at index 0.
    """
    if period < 1:
        return [None] * len(bars)

    tr = true_range(bars)
    out: Series = [None] * len(bars)
    if len(bars) <= period:
        return out

    window = 0.0
    for i in range(1, period + 1):
        value = tr[i]
        if value is None:
            return out
        window += value
    out[period] = window / period

    for i in range(period + 1, len(bars)):
        current, leaving = tr[i], tr[i - period]
        if current is None or leaving is None:
            continue
        window += current - leaving
        out[i] = window / period
    return out


def _wilder_smooth(values: Series, period: int, first_index: int) -> Series:
    """Wilder's smoothing: seed with a sum, then ``s = s - s/period + v``.

    Used by ADX for +DM, -DM and TR. Not used by ATR — see the note there.
    """
    out: Series = [None] * len(values)
    if first_index + period > len(values):
        return out

    total = 0.0
    for i in range(first_index, first_index + period):
        value = values[i]
        if value is None:
            return out
        total += value
    out[first_index + period - 1] = total

    for i in range(first_index + period, len(values)):
        value = values[i]
        if value is None:
            continue
        total = total - total / period + value
        out[i] = total
    return out


def adx(bars: list[Bar], period: int = 14) -> Series:
    """Average Directional Index (Wilder).

    Directional movement, smoothed the Wilder way, turned into +DI / -DI, then
    DX, then ADX as a Wilder average of DX. The first ADX value therefore needs
    roughly ``2 * period`` bars, which is why the scanner insists on a few
    hundred bars before it will analyse a symbol at all.
    """
    count = len(bars)
    if period < 1 or count < 2:
        return [None] * count

    plus_dm: Series = [None] * count
    minus_dm: Series = [None] * count
    tr = true_range(bars)

    for i in range(1, count):
        up_move = bars[i].high - bars[i - 1].high
        down_move = bars[i - 1].low - bars[i].low
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0.0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0.0) else 0.0

    smooth_plus = _wilder_smooth(plus_dm, period, 1)
    smooth_minus = _wilder_smooth(minus_dm, period, 1)
    smooth_tr = _wilder_smooth(tr, period, 1)

    dx: Series = [None] * count
    for i in range(count):
        sp, sm, st = smooth_plus[i], smooth_minus[i], smooth_tr[i]
        if sp is None or sm is None or st is None or st <= 0.0:
            continue
        plus_di = 100.0 * sp / st
        minus_di = 100.0 * sm / st
        total_di = plus_di + minus_di
        dx[i] = 0.0 if total_di <= 0.0 else 100.0 * abs(plus_di - minus_di) / total_di

    first_dx = next((i for i, value in enumerate(dx) if value is not None), None)
    if first_dx is None:
        return [None] * count

    out: Series = [None] * count
    window: list[float] = []
    current: float | None = None
    for i in range(first_dx, count):
        value = dx[i]
        if value is None:
            continue
        if current is None:
            window.append(value)
            if len(window) == period:
                current = sum(window) / period
                out[i] = current
        else:
            current = (current * (period - 1) + value) / period
            out[i] = current
    return out


def median(values: list[float]) -> float:
    """Median of a non-empty list; ``0.0`` for an empty one.

    Defined here rather than reaching for ``statistics.median`` so the
    even-length averaging matches the MQL5 original exactly.
    """
    count = len(values)
    if count == 0:
        return 0.0
    ordered = sorted(values)
    if count % 2 == 1:
        return ordered[count // 2]
    return (ordered[count // 2 - 1] + ordered[count // 2]) / 2.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def last_defined(series: Series, count: int) -> list[float] | None:
    """The last ``count`` defined values, or ``None`` if there are not that many.

    Callers use this instead of indexing so a partially warmed indicator can
    never leak a ``None`` into the arithmetic.
    """
    defined = [v for v in series if v is not None]
    if len(defined) < count:
        return None
    return defined[-count:]
