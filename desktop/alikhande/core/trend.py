"""Multi-timeframe trend classification.

The scoring model is inherited from v1.1.0 and deliberately unchanged — it is
the part of the system that was actually reviewed and corrected, including two
fixes worth preserving explicitly:

* EMA slope reads the correct chronological ends of the buffer. (The
  chronological convention in ``indicators`` makes this one impossible to get
  wrong again: ``fast[-1]`` is unambiguously the newest value.)
* Strength is a *magnitude*; direction carries the sign. Callers must apply
  strength only to the side the direction already favours, or a bearish trend
  ends up inflating the long score — the "two-sided strength" bug.
  ``directional_bonus`` below is the only sanctioned way to consume it.
"""

from __future__ import annotations

from ..config import StructureConfig
from .enums import Direction, Timeframe, TrendClass
from .indicators import adx, atr, closes, clamp, ema, median
from .models import Bar, TrendResult

# EMA and ADX/ATR periods. Fixed rather than configurable: they are part of what
# RULE_VERSION identifies, and making them tunable would let two runs with the
# same rule version mean different things.
EMA_FAST_PERIOD = 50
EMA_SLOW_PERIOD = 200
ADX_PERIOD = 14
ATR_PERIOD = 14


def classify(direction_score: float) -> TrendClass:
    if direction_score >= 75:
        return TrendClass.STRONG_BULLISH
    if direction_score >= 45:
        return TrendClass.BULLISH
    if direction_score >= 20:
        return TrendClass.WEAK_BULLISH
    if direction_score <= -75:
        return TrendClass.STRONG_BEARISH
    if direction_score <= -45:
        return TrendClass.BEARISH
    if direction_score <= -20:
        return TrendClass.WEAK_BEARISH
    return TrendClass.NEUTRAL


class TrendEngine:
    """Scores one symbol on one timeframe."""

    def __init__(self, structure: StructureConfig | None = None) -> None:
        self._structure = structure or StructureConfig()

    def analyze(
        self,
        bars: list[Bar],
        timeframe: Timeframe,
        point: float,
        *,
        include_forming_bar: bool = False,
    ) -> TrendResult:
        """Analyse ``bars`` (chronological, oldest first).

        The most recent bar is assumed to be **still forming** and is dropped
        before anything is computed. Acting on a forming bar is look-ahead: its
        high, low and close all still move. ``include_forming_bar=True`` exists
        for replay over already-closed data, where the caller knows the last
        bar is complete.
        """
        out = TrendResult(timeframe=timeframe)

        closed = bars if include_forming_bar else bars[:-1]
        lookback = self._structure.atr_quality_lookback

        # Enough history for the slow EMA to mean anything, for ADX to warm up,
        # and for the ATR median window to be full.
        required = max(EMA_SLOW_PERIOD, 2 * ADX_PERIOD + 2, ATR_PERIOD + lookback) + 5
        if len(closed) < required or point <= 0.0:
            return out

        price = closes(closed)
        fast_series = ema(price, EMA_FAST_PERIOD)
        slow_series = ema(price, EMA_SLOW_PERIOD)
        adx_series = adx(closed, ADX_PERIOD)
        atr_series = atr(closed, ATR_PERIOD)

        fast_defined = [v for v in fast_series if v is not None]
        slow_defined = [v for v in slow_series if v is not None]
        adx_defined = [v for v in adx_series if v is not None]
        atr_defined = [v for v in atr_series if v is not None]

        if len(fast_defined) < 3 or not slow_defined or not adx_defined:
            return out
        if len(atr_defined) < lookback:
            return out

        # Three most recent closed bars. ``recent[-1]`` is the newest.
        recent = closed[-3:]
        ema_fast_now = fast_defined[-1]
        ema_fast_old = fast_defined[-3]
        ema_slow_now = slow_defined[-1]
        atr_now = atr_defined[-1]
        atr_median = median(atr_defined[-lookback:])

        if atr_now <= 0.0:
            return out

        # Swing structure over the last three closed bars: higher high AND
        # higher low, or the mirror image. Anything else contributes nothing.
        newest, oldest = recent[-1], recent[0]
        structure = 0.0
        if newest.high > oldest.high and newest.low > oldest.low:
            structure = 40.0
        elif newest.high < oldest.high and newest.low < oldest.low:
            structure = -40.0

        alignment = 20.0 if ema_fast_now > ema_slow_now else -20.0
        slope = clamp((ema_fast_now - ema_fast_old) / point, -15.0, 15.0)
        location = 10.0 if newest.close > ema_fast_now else -10.0
        direction_score = clamp(structure + alignment + slope + location, -100.0, 100.0)

        # A trend nobody is trading is not a trend: ADX scales conviction down,
        # and an ATR far from its own median means the regime is unreliable.
        adx_now = adx_defined[-1]
        adx_multiplier = clamp((adx_now - 12.0) / 18.0, 0.35, 1.0)
        atr_ratio = atr_now / atr_median if atr_median > 0.0 else 1.0

        volatility_multiplier = 1.0
        if (
            atr_ratio < self._structure.atr_quality_floor_ratio
            or atr_ratio > self._structure.atr_quality_ceiling_ratio
        ):
            volatility_multiplier = 0.60
        elif atr_ratio < 0.75 or atr_ratio > 1.75:
            volatility_multiplier = 0.80

        out.direction_score = direction_score
        out.strength = abs(direction_score) * adx_multiplier * volatility_multiplier
        out.trend_class = classify(direction_score)
        out.ema_fast = ema_fast_now
        out.ema_slow = ema_slow_now
        out.adx = adx_now
        out.atr = atr_now
        out.atr_ratio = atr_ratio
        # The moment this information first became knowable: the close of the
        # most recent closed bar.
        out.available_information_time = newest.time + timeframe.seconds
        out.valid = True
        return out


def directional_bonus(trend: TrendResult, wanted: Direction) -> float:
    """Strength contribution for one timeframe toward one side.

    Returns 0 for a neutral trend — neither side earns a bonus — and 0 when the
    trend opposes the requested direction. Consuming ``strength`` directly
    instead of going through here is how the two-sided inflation bug happens.
    """
    if not trend.valid or wanted == Direction.NONE:
        return 0.0
    if trend.direction_score == 0.0:
        return 0.0
    trend_is_long = trend.direction_score > 0.0
    want_long = wanted == Direction.LONG
    if trend_is_long != want_long:
        return 0.0
    return trend.strength
