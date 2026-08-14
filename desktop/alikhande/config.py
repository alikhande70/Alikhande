"""Centralised defaults and the assumption registry.

Ported from ``Core/Config.mqh`` with its discipline intact:

``[ASSUMED]``
    A working default that has NOT been validated against a live broker or
    account. Treat it as a hypothesis, not a setting. The acceptance run on the
    target account is what turns an ``[ASSUMED]`` into a fact.

``[POLICY]``
    A project decision. Not tunable downward without an explicit policy change,
    and several are enforced structurally elsewhere in the codebase.

Values live in a frozen dataclass rather than module constants so a run can be
configured without mutating global state — which matters here in a way it did
not in MQL5, because the desktop build can hold a live session and a replay
session in the same process.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class ScanConfig:
    """Scheduling and data-quality thresholds."""

    scan_interval_ms: int = 250  # [ASSUMED]
    symbols_per_slice: int = 2  # [ASSUMED]
    minimum_bars: int = 300  # [ASSUMED]
    max_tick_age_seconds: int = 10  # [ASSUMED]
    spread_warmup_samples: int = 30  # [ASSUMED]
    spread_sample_capacity: int = 240  # [ASSUMED]

    spread_normal_max_ratio: float = 1.30  # [ASSUMED]
    spread_elevated_max_ratio: float = 1.70  # [ASSUMED]
    spread_high_max_ratio: float = 2.20  # [ASSUMED]


@dataclass(frozen=True)
class StructureConfig:
    """Volatility and structural-zone parameters."""

    atr_quality_floor_ratio: float = 0.50  # [ASSUMED]
    atr_quality_ceiling_ratio: float = 2.50  # [ASSUMED]
    atr_quality_lookback: int = 100  # [ASSUMED]

    zone_lookback_bars: int = 300  # [ASSUMED]
    zone_pivot_left: int = 3  # [ASSUMED]
    zone_pivot_right: int = 3  # [ASSUMED]
    zone_width_atr_fraction: float = 0.20  # [ASSUMED]
    zone_proximity_atr: float = 1.50  # [ASSUMED] max distance to be "at" a zone
    stop_buffer_atr: float = 0.15  # [ASSUMED] beyond the zone edge
    max_stop_distance_atr: float = 2.50  # [ASSUMED] reject absurd stops


@dataclass(frozen=True)
class ScoringConfig:
    """Rule-score thresholds. A rule score is not a probability."""

    score_threshold: float = 75.0  # [ASSUMED]
    score_separation: float = 10.0  # [ASSUMED] winner must lead by this much
    signal_ttl_seconds: int = 900  # [ASSUMED] 15 min candidate lifetime


@dataclass(frozen=True)
class RiskConfig:
    """Risk policy. The [POLICY] values here are the ones that make the system
    refuse trades rather than resize them."""

    risk_percent: float = 0.25  # [POLICY] default per-trade risk
    maximum_risk_percent: float = 0.50  # [POLICY] hard ceiling per trade
    minimum_risk_reward: float = 2.00  # [POLICY] hard floor
    rounding_tolerance: float = 1.01  # [POLICY] max 1% overshoot from rounding

    max_open_risk_pct: float = 1.00  # [ASSUMED] aggregate across open trades
    max_currency_risk_pct: float = 0.75  # [ASSUMED] per currency leg
    max_asset_class_risk_pct: float = 1.00  # [ASSUMED]

    guards_enabled: bool = False  # circuit breakers off by default, as in v1.x
    daily_loss_limit_pct: float = 3.00  # [ASSUMED]
    total_drawdown_limit_pct: float = 8.00  # [ASSUMED]
    max_consecutive_losses: int = 5  # [ASSUMED]


@dataclass(frozen=True)
class ExecutionConfig:
    """Execution timings and the two-step arming window."""

    preview_ttl_seconds: int = 30  # [ASSUMED]
    max_drift_points: float = 30.0  # [ASSUMED] symbol-specific validation needed
    reconcile_grace_seconds: int = 30  # [ASSUMED] before an unknown is escalated
    # How long an armed intent stays confirmable. Short on purpose: the point of
    # arming is that the operator evaluated *this* plan at *this* price, and
    # that claim decays quickly.
    arm_ttl_seconds: int = 20  # [ASSUMED]
    magic: int = 20260806
    order_comment: str = "AlikhandeScanner"


@dataclass(frozen=True)
class NewsConfig:
    pre_minutes: int = 30  # [ASSUMED]
    post_minutes: int = 15  # [ASSUMED]
    include_medium_importance: bool = False  # [ASSUMED]


@dataclass(frozen=True)
class StatisticsConfig:
    # Below this sample count no probability is displayed at all. A rule score
    # is not a probability, and a probability from 8 trades is not evidence.
    min_outcome_sample: int = 30  # [POLICY]
    confidence_z: float = 1.96  # 95% Wilson interval


DEFAULT_SYMBOLS: tuple[str, ...] = (
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
)


@dataclass(frozen=True)
class AppConfig:
    """The whole configuration, in one immutable object."""

    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    scan: ScanConfig = field(default_factory=ScanConfig)
    structure: StructureConfig = field(default_factory=StructureConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    statistics: StatisticsConfig = field(default_factory=StatisticsConfig)

    def with_symbols(self, symbols: tuple[str, ...]) -> "AppConfig":
        return replace(self, symbols=tuple(symbols))

    def parameter_fingerprint_source(self) -> str:
        """The exact tunables that shape scoring, in a stable textual form.

        Stamped onto every persisted signal via ``core.hashing.fnv1a64`` so a
        stored result can be tied to the configuration that made it. Changing
        any of these invalidates comparison against older signals, which is the
        entire point of recording it.
        """
        s, c, r = self.structure, self.scoring, self.risk
        return (
            f"prox={s.zone_proximity_atr:.3f};"
            f"stopbuf={s.stop_buffer_atr:.3f};"
            f"maxstop={s.max_stop_distance_atr:.3f};"
            f"rr={r.minimum_risk_reward:.3f};"
            f"thr={c.score_threshold:.1f};"
            f"sep={c.score_separation:.1f};"
            f"zlb={s.zone_lookback_bars:d};"
            f"zl={s.zone_pivot_left:d};"
            f"zr={s.zone_pivot_right:d};"
            f"zw={s.zone_width_atr_fraction:.3f}"
        )


def assumption_registry() -> list[dict[str, Any]]:
    """Every value the build has assumed rather than measured.

    Surfaced verbatim on the Health tab. A number the operator can see labelled
    ``[ASSUMED]`` is a number they can go and check; a number buried in source
    is one they will trust by default.
    """
    cfg = AppConfig()
    return [
        {"key": "scan_interval_ms", "value": cfg.scan.scan_interval_ms, "kind": "ASSUMED"},
        {"key": "minimum_bars", "value": cfg.scan.minimum_bars, "kind": "ASSUMED"},
        {"key": "max_tick_age_seconds", "value": cfg.scan.max_tick_age_seconds, "kind": "ASSUMED"},
        {"key": "spread_warmup_samples", "value": cfg.scan.spread_warmup_samples, "kind": "ASSUMED"},
        {"key": "zone_lookback_bars", "value": cfg.structure.zone_lookback_bars, "kind": "ASSUMED"},
        {"key": "zone_proximity_atr", "value": cfg.structure.zone_proximity_atr, "kind": "ASSUMED"},
        {"key": "stop_buffer_atr", "value": cfg.structure.stop_buffer_atr, "kind": "ASSUMED"},
        {"key": "max_stop_distance_atr", "value": cfg.structure.max_stop_distance_atr, "kind": "ASSUMED"},
        {"key": "score_threshold", "value": cfg.scoring.score_threshold, "kind": "ASSUMED"},
        {"key": "score_separation", "value": cfg.scoring.score_separation, "kind": "ASSUMED"},
        {"key": "max_drift_points", "value": cfg.execution.max_drift_points, "kind": "ASSUMED"},
        {"key": "reconcile_grace_seconds", "value": cfg.execution.reconcile_grace_seconds, "kind": "ASSUMED"},
        {"key": "arm_ttl_seconds", "value": cfg.execution.arm_ttl_seconds, "kind": "ASSUMED"},
        {"key": "risk_percent", "value": cfg.risk.risk_percent, "kind": "POLICY"},
        {"key": "maximum_risk_percent", "value": cfg.risk.maximum_risk_percent, "kind": "POLICY"},
        {"key": "minimum_risk_reward", "value": cfg.risk.minimum_risk_reward, "kind": "POLICY"},
        {"key": "rounding_tolerance", "value": cfg.risk.rounding_tolerance, "kind": "POLICY"},
        {"key": "min_outcome_sample", "value": cfg.statistics.min_outcome_sample, "kind": "POLICY"},
    ]
