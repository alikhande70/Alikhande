"""Signal generation, split into a cached structural half and a live half.

This split is the fix for the most dangerous defect in v1.1.0. There, the whole
candidate — including entry, stop, target and the "is price at a zone?"
decision — was computed once per closed bar and then displayed and alerted
against a *live* quote until the next bar closed. On M5 that is up to five
minutes during which the panel shows LONG at an entry price the market left
long ago, and the logged entry is not the entry a human would get.

The structural half (multi-timeframe trend, zones, regime) genuinely only
changes on bar close and stays cached. The live half — zone proximity, entry,
stop, target, spread state — is recomputed on every pass against the current
quote. A signal is therefore never older than the tick it is shown with.

**A score produced here is a rule score, not a probability.** It is a weighted
sum of conditions the author believes matter; nothing in it has been validated
against outcomes. Probability lives in the ``historical_*`` fields of
``SignalCandidate`` and only appears once a real outcome sample exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import AppConfig
from ..version import RULE_VERSION, SCORING_VERSION
from .enums import Direction, Regime, SetupType, SignalState, SpreadState, Timeframe, ZoneRelation, ZoneType
from .hashing import fnv1a, fnv1a64
from .indicators import clamp
from .models import (
    Bar,
    RegimeResult,
    ScoreComponent,
    SignalCandidate,
    SymbolSnapshot,
    TrendResult,
    Zone,
)
from .regime import RegimeEngine
from .trend import TrendEngine, directional_bonus
from .zones import ZoneEngine, find_nearest_zone, find_zone_beyond, zone_anchors, zone_relation


def parameter_hash(config: AppConfig) -> str:
    """Fingerprint of the tunables that shape scoring.

    Stamped onto every persisted signal so a stored result can be tied to the
    exact configuration that made it; changing any of them invalidates
    comparison against older signals.
    """
    return fnv1a64(config.parameter_fingerprint_source())


def evidence_signal_id(
    signal: SignalCandidate,
    broker_spec_hash: str,
    *,
    namespace: str = "",
) -> str:
    """Identity of one evidence lifecycle, not merely one chart pattern.

    ``SignalEngine.evaluate`` first produces the legacy structural id because
    the broker specification is not available inside the pure signal engine.
    Persistence must be stricter: the same bar/setup under different parameters
    or a different contract specification is not the same experiment.  This
    second-stage 64-bit id scopes the structural fact by every versioned input
    that changes its meaning.  Replays additionally supply their UUID run id as
    ``namespace`` so two datasets cannot share a lifecycle.
    """
    return fnv1a64(
        "|".join(
            (
                namespace,
                signal.signal_id,
                signal.symbol,
                str(int(signal.direction)),
                str(int(signal.setup)),
                str(int(signal.confirmation_bar_time)),
                signal.rule_version,
                signal.scoring_version,
                signal.parameter_hash,
                broker_spec_hash,
            )
        )
    )


@dataclass
class StructuralContext:
    """The half that only changes on bar close."""

    symbol: str = ""
    h4: TrendResult = field(default_factory=TrendResult)
    h1: TrendResult = field(default_factory=TrendResult)
    m15: TrendResult = field(default_factory=TrendResult)
    m5: TrendResult = field(default_factory=TrendResult)
    zones: list[Zone] = field(default_factory=list)
    regime: RegimeResult = field(default_factory=RegimeResult)
    built_at: int = 0
    valid: bool = False


class SignalEngine:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or AppConfig()
        self._trend = TrendEngine(self._config.structure)
        self._zones = ZoneEngine(self._config.structure)
        self._regime = RegimeEngine(self._config.structure)
        self._parameter_hash = parameter_hash(self._config)

    # --------------------------------------------------------------- structure
    def build_context(
        self,
        symbol: str,
        bars_by_timeframe: dict[Timeframe, list[Bar]],
        snapshot: SymbolSnapshot,
        *,
        include_forming_bar: bool = False,
        now: int = 0,
    ) -> StructuralContext:
        """Rebuild the cached structural half.

        Called only when a closed bar changed on any analysed timeframe. A
        missing or too-short series on any required timeframe yields an invalid
        context rather than a partial one — half a multi-timeframe picture is
        not a cheaper version of the whole, it is a different and wrong picture.
        """
        ctx = StructuralContext(symbol=symbol, built_at=now)

        required = (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)
        results: dict[Timeframe, TrendResult] = {}
        for timeframe in required:
            bars = bars_by_timeframe.get(timeframe, [])
            result = self._trend.analyze(
                bars,
                timeframe,
                snapshot.point,
                include_forming_bar=include_forming_bar,
            )
            if not result.valid:
                return ctx
            results[timeframe] = result

        ctx.h4 = results[Timeframe.H4]
        ctx.h1 = results[Timeframe.H1]
        ctx.m15 = results[Timeframe.M15]
        ctx.m5 = results[Timeframe.M5]

        ctx.zones = self._zones.build(
            symbol,
            bars_by_timeframe.get(Timeframe.H1, []),
            Timeframe.H1,
            snapshot.point,
            include_forming_bar=include_forming_bar,
        )
        ctx.regime = self._regime.classify(ctx.h4, ctx.h1, snapshot)
        ctx.valid = True
        return ctx

    # -------------------------------------------------------------------- live
    def evaluate(
        self, ctx: StructuralContext, snapshot: SymbolSnapshot, now: int
    ) -> SignalCandidate:
        """Score the live quote against the cached structure.

        Called on EVERY scan pass. Cheap: no indicator work, no history reads —
        just arithmetic over the cached structure.
        """
        cfg = self._config
        s = SignalCandidate(symbol=ctx.symbol)
        s.rule_version = RULE_VERSION
        s.scoring_version = SCORING_VERSION
        s.parameter_hash = self._parameter_hash
        s.creation_time = now
        s.expires_at = now + cfg.scoring.signal_ttl_seconds
        s.regime = ctx.regime.regime if ctx.regime.valid else Regime.UNKNOWN

        if not ctx.valid:
            s.validation_codes.append("NO_STRUCTURE")
            s.hard_blocked = True
            return s

        atr = ctx.h1.atr
        if atr <= 0.0:
            s.validation_codes.append("NO_ATR")
            s.hard_blocked = True
            return s

        # ---- structure relative to the LIVE quote ---------------------------
        proximity = atr * cfg.structure.zone_proximity_atr
        demand_index = find_nearest_zone(ctx.zones, ZoneType.DEMAND, snapshot.bid, proximity)
        supply_index = find_nearest_zone(ctx.zones, ZoneType.SUPPLY, snapshot.ask, proximity)

        s.nearest_support = ctx.zones[demand_index].center if demand_index >= 0 else 0.0
        s.nearest_resistance = ctx.zones[supply_index].center if supply_index >= 0 else 0.0

        # Proximity alone is not interaction. A zone 1.4 ATR away is "near" by
        # the search radius but price is not engaging with it, and a pullback
        # setup that fires on mere nearness is describing a different trade from
        # the one it claims. The relation makes the distinction explicit and the
        # score breakdown records which case fired.
        s.demand_relation = (
            zone_relation(ctx.zones[demand_index], snapshot.bid)
            if demand_index >= 0
            else ZoneRelation.UNAVAILABLE
        )
        s.supply_relation = (
            zone_relation(ctx.zones[supply_index], snapshot.ask)
            if supply_index >= 0
            else ZoneRelation.UNAVAILABLE
        )

        # A zone may only anchor a trade in the direction it supports, AND price
        # must be on the side of it that the trade assumes.
        #
        # The second half is not pedantry. ``find_nearest_zone`` deliberately
        # does not require the zone to sit on one side of the quote — that was
        # the v1.1.0 fix which made the INSIDE case findable at all. The cost is
        # that a demand zone price has fallen *below* is still "nearest", and
        # buying it means buying support that has already broken. Worse, the
        # stop derived from it (``zone.low - buffer``) then lands ABOVE the
        # entry, and because the distance check uses an absolute value, an
        # inverted trade passes every downstream gate.
        demand_anchors = (
            demand_index >= 0
            and zone_anchors(ctx.zones[demand_index], Direction.LONG)
            and s.demand_relation in (ZoneRelation.INSIDE, ZoneRelation.ABOVE)
        )
        supply_anchors = (
            supply_index >= 0
            and zone_anchors(ctx.zones[supply_index], Direction.SHORT)
            and s.supply_relation in (ZoneRelation.INSIDE, ZoneRelation.BELOW)
        )

        long_setup = _qualify_long(ctx, demand_anchors)
        short_setup = _qualify_short(ctx, supply_anchors)

        # ---- rule score ------------------------------------------------------
        long_score = 0.0
        short_score = 0.0

        def add_long(name: str, value: float) -> None:
            nonlocal long_score
            long_score += value
            s.long_components.append(ScoreComponent(name, value))

        def add_short(name: str, value: float) -> None:
            nonlocal short_score
            short_score += value
            s.short_components.append(ScoreComponent(name, value))

        if ctx.h4.direction_score > 0.0:
            add_long("H4_BIAS", 10.0)
        elif ctx.h4.direction_score < 0.0:
            add_short("H4_BIAS", 10.0)

        # Strength only ever reaches the side its own direction favours.
        if ctx.h1.direction_score >= 20.0:
            add_long("H1_TREND", 20.0 + min(10.0, directional_bonus(ctx.h1, Direction.LONG) * 0.10))
        elif ctx.h1.direction_score <= -20.0:
            add_short("H1_TREND", 20.0 + min(10.0, directional_bonus(ctx.h1, Direction.SHORT) * 0.10))

        if long_setup != SetupType.NONE:
            add_long("SETUP", 25.0)
        if short_setup != SetupType.NONE:
            add_short("SETUP", 25.0)

        if demand_anchors:
            add_long("ZONE_QUALITY", min(15.0, ctx.zones[demand_index].quality * 0.15))
            if s.demand_relation == ZoneRelation.INSIDE:
                add_long("ZONE_INSIDE", 5.0)
        if supply_anchors:
            add_short("ZONE_QUALITY", min(15.0, ctx.zones[supply_index].quality * 0.15))
            if s.supply_relation == ZoneRelation.INSIDE:
                add_short("ZONE_INSIDE", 5.0)

        if ctx.m5.direction_score >= 15.0:
            add_long("M5_CONFIRM", 15.0)
        elif ctx.m5.direction_score <= -15.0:
            add_short("M5_CONFIRM", 15.0)

        if ctx.h1.direction_score > 0.0 and ctx.m15.direction_score > 0.0 and ctx.m5.direction_score > 0.0:
            add_long("MTF_ALIGNED", 10.0)
        if ctx.h1.direction_score < 0.0 and ctx.m15.direction_score < 0.0 and ctx.m5.direction_score < 0.0:
            add_short("MTF_ALIGNED", 10.0)

        if snapshot.spread_state == SpreadState.NORMAL:
            add_long("SPREAD_NORMAL", 5.0)
            add_short("SPREAD_NORMAL", 5.0)
        elif snapshot.spread_state == SpreadState.ELEVATED:
            add_long("SPREAD_ELEVATED", 2.0)
            add_short("SPREAD_ELEVATED", 2.0)

        # ---- penalties and hard blocks ---------------------------------------
        hard = False

        if ctx.h4.direction_score <= -45.0 and ctx.h1.direction_score >= 45.0:
            add_long("H4_H1_CONFLICT", -30.0)
            s.validation_codes.append("H4_H1_CONFLICT_LONG")
        if ctx.h4.direction_score >= 45.0 and ctx.h1.direction_score <= -45.0:
            add_short("H4_H1_CONFLICT", -30.0)
            s.validation_codes.append("H4_H1_CONFLICT_SHORT")

        if snapshot.spread_state in (
            SpreadState.HIGH,
            SpreadState.EXTREME,
            SpreadState.STALE,
            SpreadState.NO_TICK,
            SpreadState.WARMING_UP,
        ):
            hard = True
            s.validation_codes.append("SPREAD_OR_QUOTE_BLOCK")

        if long_setup == SetupType.NONE and short_setup == SetupType.NONE:
            s.validation_codes.append("NO_CONFIRMED_SETUP")

        s.long_score = clamp(long_score, 0.0, 100.0)
        s.short_score = clamp(short_score, 0.0, 100.0)

        # ---- direction selection ---------------------------------------------
        direction = Direction.NONE
        setup = SetupType.NONE
        threshold = cfg.scoring.score_threshold
        separation = cfg.scoring.score_separation

        if (
            not hard
            and long_setup != SetupType.NONE
            and s.long_score >= threshold
            and s.long_score - s.short_score >= separation
        ):
            direction, setup = Direction.LONG, long_setup
        elif (
            not hard
            and short_setup != SetupType.NONE
            and s.short_score >= threshold
            and s.short_score - s.long_score >= separation
        ):
            direction, setup = Direction.SHORT, short_setup

        # ---- structural stop and 2R target -----------------------------------
        entry = stop = target = 0.0
        if direction != Direction.NONE:
            entry = snapshot.bid if direction == Direction.SHORT else snapshot.ask
            buffer = max(atr * cfg.structure.stop_buffer_atr, snapshot.point * 5.0)

            if direction == Direction.LONG:
                stop = ctx.zones[demand_index].low - buffer
            else:
                stop = ctx.zones[supply_index].high + buffer

            # A stop must sit on the LOSING side of the entry. Checking the
            # signed relationship before the distance is the whole point: an
            # absolute distance cannot tell an inverted trade from a valid one,
            # and an inverted trade is not a wide stop, it is a position whose
            # stop and target are both in the same direction.
            inverted = (direction == Direction.LONG and stop >= entry) or (
                direction == Direction.SHORT and stop <= entry
            )
            risk_distance = abs(entry - stop)

            if inverted:
                hard = True
                s.validation_codes.append("STOP_ON_WRONG_SIDE_OF_ENTRY")
            elif risk_distance <= 0.0 or risk_distance > atr * cfg.structure.max_stop_distance_atr:
                hard = True
                s.validation_codes.append("INVALID_STRUCTURAL_STOP")
            else:
                rr = cfg.risk.minimum_risk_reward
                target = (
                    entry + rr * risk_distance
                    if direction == Direction.LONG
                    else entry - rr * risk_distance
                )

                # An opposing level inside the road to target means the 2R is
                # arithmetic, not something the market is likely to deliver.
                if direction == Direction.LONG:
                    blocking = find_zone_beyond(ctx.zones, ZoneType.SUPPLY, entry, True)
                    if blocking >= 0 and ctx.zones[blocking].low < target:
                        hard = True
                        s.validation_codes.append("OPPOSING_ZONE_BEFORE_2R")
                else:
                    blocking = find_zone_beyond(ctx.zones, ZoneType.DEMAND, entry, False)
                    if blocking >= 0 and ctx.zones[blocking].high > target:
                        hard = True
                        s.validation_codes.append("OPPOSING_ZONE_BEFORE_2R")

        # A hard block clears BOTH direction and setup. v1.1.0 cleared only
        # direction, leaving a phantom setup on a blocked candidate.
        if hard:
            direction = Direction.NONE
            setup = SetupType.NONE
            entry = stop = target = 0.0

        s.direction = direction
        s.setup = setup
        s.hard_blocked = hard
        s.preferred_entry = entry
        s.entry_low = entry - atr * 0.10 if entry > 0.0 else 0.0
        s.entry_high = entry + atr * 0.10 if entry > 0.0 else 0.0
        s.stop_loss = stop
        s.take_profit = target
        s.confirmation_bar_time = ctx.m5.available_information_time

        # Identity is keyed on the structural situation, not on the live price:
        # the same setup re-evaluated a few seconds later at a slightly
        # different quote is the SAME signal, and must not be logged twice.
        s.signal_id = fnv1a(
            f"{ctx.symbol}|{int(direction)}|{int(setup)}|{s.confirmation_bar_time}|{RULE_VERSION}"
        )

        if direction != Direction.NONE:
            s.state = SignalState.CONFIRMED
        elif hard:
            s.state = SignalState.NONE
        else:
            s.state = SignalState.CANDIDATE
        return s


# Qualification requires an actual pullback or rejection, not merely a
# directional bias. Both branches demand M5 confirmation.


def _qualify_long(ctx: StructuralContext, at_demand: bool) -> SetupType:
    if not at_demand:
        return SetupType.NONE
    if (
        ctx.h1.direction_score >= 20.0
        and ctx.m15.direction_score > -20.0
        and ctx.m5.direction_score >= 15.0
    ):
        return SetupType.TREND_PULLBACK
    if (
        ctx.h1.direction_score > -45.0
        and ctx.m15.direction_score >= 0.0
        and ctx.m5.direction_score >= 20.0
    ):
        return SetupType.SUPPORT_REJECTION
    return SetupType.NONE


def _qualify_short(ctx: StructuralContext, at_supply: bool) -> SetupType:
    if not at_supply:
        return SetupType.NONE
    if (
        ctx.h1.direction_score <= -20.0
        and ctx.m15.direction_score < 20.0
        and ctx.m5.direction_score <= -15.0
    ):
        return SetupType.TREND_PULLBACK
    if (
        ctx.h1.direction_score < 45.0
        and ctx.m15.direction_score <= 0.0
        and ctx.m5.direction_score <= -20.0
    ):
        return SetupType.RESISTANCE_REJECTION
    return SetupType.NONE
