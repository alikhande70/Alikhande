"""Market regime classification.

Before asking "long or short?" the system should answer "is this market
tradeable at all, and by what kind of strategy?". A pullback setup in a dead
range and the same setup in a clean trend are not the same trade.

Built deliberately from measurements the system already computes — ADX, the
ATR-to-median ratio, EMA alignment across H4/H1, and the spread state — rather
than a new indicator stack. The classification is only as good as its inputs,
and adding more inputs before the outcome database can score them would be
guessing with extra steps.

The regime is ADVISORY: it is recorded on every signal and shown on the
dashboard, but it does not gate signals. Gating on it is a decision for when
there is outcome data to justify the threshold.
"""

from __future__ import annotations

from ..config import StructureConfig
from .enums import Regime, SpreadState
from .indicators import clamp
from .models import RegimeResult, SymbolSnapshot, TrendResult


class RegimeEngine:
    def __init__(self, structure: StructureConfig | None = None) -> None:
        self._structure = structure or StructureConfig()

    def classify(
        self, h4: TrendResult, h1: TrendResult, snapshot: SymbolSnapshot
    ) -> RegimeResult:
        cfg = self._structure

        if not h4.valid or not h1.valid:
            return RegimeResult(reason="TREND_DATA_UNAVAILABLE")

        # An unusable spread makes the regime question moot — nothing should be
        # traded here regardless of what the trend looks like.
        if snapshot.spread_state in (SpreadState.EXTREME, SpreadState.HIGH):
            return RegimeResult(
                regime=Regime.ILLIQUID,
                confidence=90.0,
                reason=f"SPREAD_{snapshot.spread_state.name}",
                valid=True,
            )

        aligned_up = h4.direction_score > 0.0 and h1.direction_score >= 20.0
        aligned_down = h4.direction_score < 0.0 and h1.direction_score <= -20.0

        # ADX is the trend/range discriminator; the ATR ratio separates a
        # healthy trend from a volatility event, and a dead tape from a range.
        adx_value = max(h1.adx, 0.0)
        atr_ratio = h1.atr_ratio

        if atr_ratio > cfg.atr_quality_ceiling_ratio:
            return RegimeResult(
                regime=Regime.VOLATILE,
                confidence=100.0 * clamp(atr_ratio - cfg.atr_quality_ceiling_ratio, 0.0, 1.0),
                reason=f"ATR_RATIO_{atr_ratio:.2f}_ABOVE_CEILING",
                valid=True,
            )
        if atr_ratio < cfg.atr_quality_floor_ratio:
            return RegimeResult(
                regime=Regime.QUIET,
                confidence=100.0
                * clamp((cfg.atr_quality_floor_ratio - atr_ratio) / 0.5, 0.0, 1.0),
                reason=f"ATR_RATIO_{atr_ratio:.2f}_BELOW_FLOOR",
                valid=True,
            )
        if aligned_up and adx_value >= 20.0:
            return RegimeResult(
                regime=Regime.TREND_UP,
                confidence=100.0 * clamp((adx_value - 15.0) / 25.0, 0.0, 1.0),
                reason=f"H4_H1_ALIGNED_UP_ADX_{adx_value:.0f}",
                valid=True,
            )
        if aligned_down and adx_value >= 20.0:
            return RegimeResult(
                regime=Regime.TREND_DOWN,
                confidence=100.0 * clamp((adx_value - 15.0) / 25.0, 0.0, 1.0),
                reason=f"H4_H1_ALIGNED_DOWN_ADX_{adx_value:.0f}",
                valid=True,
            )
        return RegimeResult(
            regime=Regime.RANGE,
            confidence=100.0 * clamp((25.0 - adx_value) / 25.0, 0.0, 1.0),
            reason=f"NO_MTF_ALIGNMENT_ADX_{adx_value:.0f}",
            valid=True,
        )
