"""The feature snapshot stored alongside every signal.

One definition, used by both the live scan and the backtest. Two copies would
drift, and the moment they did, a model trained on backtest features would be
scoring live signals against subtly different inputs — a failure that produces
plausible numbers rather than an error.

This is what a future model would train on. Capturing it now, before any model
exists, is the reason one becomes possible later without re-running history:
the live quote, the spread and the structural state at the instant of a signal
are not recoverable afterwards from bars alone.
"""

from __future__ import annotations

from .models import SignalCandidate, SymbolSnapshot


def extract(context, signal: SignalCandidate, snapshot: SymbolSnapshot) -> dict[str, float]:
    """Flatten the structural context and live quote into named numbers."""
    return {
        "h4_direction": context.h4.direction_score,
        "h1_direction": context.h1.direction_score,
        "m15_direction": context.m15.direction_score,
        "m5_direction": context.m5.direction_score,
        "h4_strength": context.h4.strength,
        "h1_strength": context.h1.strength,
        "h1_adx": context.h1.adx,
        "h1_atr": context.h1.atr,
        "h1_atr_ratio": context.h1.atr_ratio,
        "zone_count": float(len(context.zones)),
        "regime": float(int(context.regime.regime)),
        "regime_confidence": context.regime.confidence,
        "spread_points": snapshot.spread_points,
        "spread_ratio": snapshot.spread_ratio,
        "spread_percentile": snapshot.spread_percentile,
        "demand_relation": float(int(signal.demand_relation)),
        "supply_relation": float(int(signal.supply_relation)),
        "long_score": signal.long_score,
        "short_score": signal.short_score,
    }
