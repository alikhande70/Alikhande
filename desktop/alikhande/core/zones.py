"""Structural supply/demand zones from confirmed swing pivots.

Two corrections against v1.1.0, both preserved from the MQL5 rebuild:

1. **Zones are typed.** v1.1.0 merged any two pivots whose ATR-scaled bands
   overlapped, regardless of whether they came from swing highs or swing lows,
   and incremented one shared ``touches`` counter. A band containing three
   highs and three lows scored as six touches, and ``touches`` feeds
   ``quality``, which feeds the signal score. Supply and demand are separate
   populations here and only merge with their own kind.

2. **Zones are found relative to price, not by a strict inequality against the
   current quote.** The consumer decides whether price is above, below or
   inside a zone — being inside one is the pullback moment the strategy exists
   to catch, and v1.1.0's nearest-zone search discarded exactly that case.

Pivot confirmation is lagged by design: a swing high at bar ``i`` is only
confirmed once ``right`` further bars have closed without exceeding it, and
``confirmation_time`` records when that became knowable. Using the pivot's own
timestamp would be look-ahead.
"""

from __future__ import annotations

from ..config import StructureConfig
from .enums import Direction, Timeframe, ZoneRelation, ZoneType
from .hashing import fnv1a
from .indicators import atr as atr_series
from .models import Bar, Zone


class ZoneEngine:
    def __init__(self, structure: StructureConfig | None = None) -> None:
        self._structure = structure or StructureConfig()

    def build(
        self,
        symbol: str,
        bars: list[Bar],
        timeframe: Timeframe,
        point: float,
        *,
        include_forming_bar: bool = False,
    ) -> list[Zone]:
        """Build the zone set from chronological ``bars``.

        As in ``TrendEngine``, the final bar is treated as still forming and
        dropped: a bar that is still moving cannot host a confirmed pivot.
        """
        cfg = self._structure
        left, right = cfg.zone_pivot_left, cfg.zone_pivot_right

        closed = bars if include_forming_bar else bars[:-1]
        if left < 1 or right < 1 or point <= 0.0:
            return []

        window = closed[-cfg.zone_lookback_bars :] if cfg.zone_lookback_bars > 0 else closed
        if len(window) < 50:
            return []

        atr_values = atr_series(window, 14)

        zones: list[Zone] = []
        # ``i`` indexes the candidate pivot. Chronological order here, so
        # ``i - k`` is older and ``i + k`` is newer — the mirror image of the
        # MQL5 original's series indexing.
        for i in range(left, len(window) - right):
            bar = window[i]
            is_high = True
            is_low = True

            for k in range(1, left + 1):
                older = window[i - k]
                if bar.high <= older.high:
                    is_high = False
                if bar.low >= older.low:
                    is_low = False
            for k in range(1, right + 1):
                newer = window[i + k]
                if bar.high < newer.high:
                    is_high = False
                if bar.low > newer.low:
                    is_low = False

            if not is_high and not is_low:
                continue
            # A single bar can be the local high AND the local low of a very
            # quiet neighbourhood. Emitting it as both would let one bar inflate
            # two zones, so an ambiguous pivot is discarded.
            if is_high and is_low:
                continue

            bar_atr = atr_values[i]
            if bar_atr is None or bar_atr <= 0.0:
                continue

            width = max(bar_atr * cfg.zone_width_atr_fraction, point * 5.0)
            price = bar.high if is_high else bar.low
            confirming = window[i + right]

            pivot = Zone(
                id=fnv1a(f"{symbol}|{timeframe.label}|{int(is_high)}|{bar.time}"),
                type=ZoneType.SUPPLY if is_high else ZoneType.DEMAND,
                timeframe=timeframe,
                low=price - width,
                high=price + width,
                center=price,
                touches=1,
                quality=30.0,
                pivot_time=bar.time,
                # Knowable only once the confirming bar closed.
                confirmation_time=confirming.time + timeframe.seconds,
                broken=False,
                valid=True,
            )
            _absorb(zones, pivot)

        return zones


def _absorb(zones: list[Zone], pivot: Zone) -> None:
    """Merge a pivot into an existing same-type zone containing its centre, or
    append it as a new zone."""
    for zone in zones:
        if zone.type != pivot.type:
            continue
        if pivot.center < zone.low or pivot.center > zone.high:
            continue

        zone.low = min(zone.low, pivot.low)
        zone.high = max(zone.high, pivot.high)
        zone.center = (zone.low + zone.high) / 2.0
        zone.touches += 1
        zone.quality = min(100.0, zone.quality + 10.0)
        # Keep the most recent confirmation: a level retested last week is more
        # relevant than the same level from six months ago.
        if pivot.confirmation_time > zone.confirmation_time:
            zone.confirmation_time = pivot.confirmation_time
        return

    zones.append(pivot)


# ------------------------------------------------------------------- lookups
#
# Free functions rather than engine methods because they are pure queries over
# an already-built zone set, and the signal engine needs several different views
# of the same set.


def find_nearest_zone(
    zones: list[Zone], zone_type: ZoneType, price: float, max_distance: float
) -> int:
    """Index of the nearest usable zone of ``zone_type`` within ``max_distance``
    of ``price``, or ``-1``.

    Unlike v1.1.0 this does NOT require the zone to sit entirely on one side of
    the quote, so a zone price is currently inside remains findable.
    """
    index = -1
    best = float("inf")
    for i, zone in enumerate(zones):
        if not zone.valid or zone.broken or zone.type != zone_type:
            continue
        distance = abs(price - zone.center)
        if distance > max_distance or distance >= best:
            continue
        best = distance
        index = i
    return index


def zone_relation(zone: Zone, price: float) -> ZoneRelation:
    """Where price sits relative to a zone.

    ``UNAVAILABLE`` is a distinct answer, not a synonym for "not inside". That
    distinction is what stops a missing zone reading as a clean rejection.
    """
    if not zone.valid or zone.broken or zone.low <= 0.0 or zone.high <= 0.0:
        return ZoneRelation.UNAVAILABLE
    if zone.low > zone.high:
        return ZoneRelation.UNAVAILABLE
    if price < zone.low:
        return ZoneRelation.BELOW
    if price > zone.high:
        return ZoneRelation.ABOVE
    return ZoneRelation.INSIDE


def price_inside_zone(zone: Zone, price: float) -> bool:
    return zone_relation(zone, price) == ZoneRelation.INSIDE


def zone_anchors(zone: Zone, direction: Direction) -> bool:
    """A zone can only anchor a trade in the direction it supports.

    Demand anchors longs, supply anchors shorts. Stated once here rather than
    re-derived at each call site, where getting it backwards is silent and
    expensive.
    """
    if not zone.valid or zone.broken:
        return False
    if direction == Direction.LONG:
        return zone.type == ZoneType.DEMAND
    if direction == Direction.SHORT:
        return zone.type == ZoneType.SUPPLY
    return False


def find_zone_beyond(
    zones: list[Zone], zone_type: ZoneType, price: float, above: bool
) -> int:
    """Nearest zone of ``zone_type`` strictly beyond ``price`` in the given
    direction — used to check whether an opposing level blocks the road to
    target."""
    index = -1
    best = float("inf")
    for i, zone in enumerate(zones):
        if not zone.valid or zone.broken or zone.type != zone_type:
            continue
        edge = zone.low if above else zone.high
        if above and edge <= price:
            continue
        if not above and edge >= price:
            continue
        distance = abs(edge - price)
        if distance >= best:
            continue
        best = distance
        index = i
    return index
