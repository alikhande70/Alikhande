"""Turns a confirmed signal into a sized, validated trade plan.

The discipline inherited from v1.1.0 and kept deliberately: **when the risk
budget buys less than the broker's minimum lot, the plan is REJECTED.** It is
never rounded up to the minimum. Rounding up silently converts "risk 0.25%" into
whatever the minimum lot happens to cost, which on a small account can be
several times the intended risk — the single most common way a careful risk
model gets quietly defeated.

Two further rules with the same character:

* Volume rounds **down**, never to nearest. Rounding to nearest can exceed the
  budget by half a step, which on a 0.01-step symbol with a tight stop is
  material.
* If the broker cannot price the stop, the plan is refused. There is no
  fallback formula. An approximation here would be a number that looks like
  risk control and is not.
"""

from __future__ import annotations

import math

from ..config import AppConfig
from .enums import Direction
from .models import (
    AccountInfo,
    PositionInfo,
    SignalCandidate,
    SymbolSpec,
    TradePlan,
)
from .portfolio import PortfolioRisk
from .ports import BrokerGateway


def volume_digits(step: float) -> int:
    """Decimal places implied by a volume step, so 0.01 renders as 0.01."""
    digits = 0
    value = step
    while digits < 8 and abs(value - round(value)) > 1e-8:
        value *= 10.0
        digits += 1
    return digits


def normalize_volume(raw: float, spec: SymbolSpec) -> tuple[float, str]:
    """Round ``raw`` down onto the broker's volume grid.

    Returns ``(volume, code)``. A non-empty ``code`` means refusal and the
    volume is meaningless.
    """
    if spec.volume_step <= 0.0 or spec.volume_min <= 0.0 or spec.volume_max < spec.volume_min:
        return 0.0, "INVALID_VOLUME_SPEC"
    if raw < spec.volume_min:
        return 0.0, f"RISK_BELOW_BROKER_MIN_VOLUME({raw:.4f}<{spec.volume_min:.2f})"

    normalized = math.floor(raw / spec.volume_step + 1e-9) * spec.volume_step
    normalized = round(normalized, volume_digits(spec.volume_step))

    if normalized < spec.volume_min or normalized > spec.volume_max:
        return 0.0, f"VOLUME_OUT_OF_RANGE({normalized:.4f})"
    return normalized, ""


class RiskPlanner:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or AppConfig()
        self._portfolio = PortfolioRisk()

    def build(
        self,
        signal: SignalCandidate,
        *,
        gateway: BrokerGateway,
        account: AccountInfo,
        spec: SymbolSpec,
        own_positions: list[PositionInfo],
        specs: dict[str, SymbolSpec],
        now: int,
        risk_percent: float | None = None,
    ) -> TradePlan:
        """Size and validate a plan.

        ``risk_percent`` is per-trade risk; portfolio caps apply on top. A plan
        that fits its own budget but breaches an aggregate cap is rejected with
        the breached cap named.
        """
        cfg = self._config
        plan = TradePlan(signal_id=signal.signal_id, symbol=signal.symbol)
        risk_pct = cfg.risk.risk_percent if risk_percent is None else risk_percent

        if signal.direction == Direction.NONE or signal.hard_blocked:
            plan.validation_codes.append("NO_ACTIONABLE_SIGNAL")
            return plan
        if risk_pct <= 0.0 or risk_pct > cfg.risk.maximum_risk_percent:
            plan.validation_codes.append(f"RISK_PERCENT_OUT_OF_POLICY({risk_pct:.2f})")
            return plan
        if signal.stop_loss <= 0.0 or signal.preferred_entry <= 0.0:
            plan.validation_codes.append("NO_STRUCTURAL_STOP")
            return plan

        equity = account.equity
        if equity <= 0.0:
            plan.validation_codes.append("NO_EQUITY")
            return plan
        risk_amount = equity * risk_pct / 100.0

        # The broker's own conversion chain. The only way to get this right for
        # a cross-currency symbol on an account denominated in a third currency.
        loss_per_lot = gateway.calc_profit(
            signal.symbol, int(signal.direction), 1.0, signal.preferred_entry, signal.stop_loss
        )
        if loss_per_lot is None:
            plan.validation_codes.append("CALC_PROFIT_UNAVAILABLE")
            return plan
        loss_per_lot = abs(loss_per_lot)
        if loss_per_lot <= 0.0:
            plan.validation_codes.append("ZERO_LOSS_PER_LOT")
            return plan

        lot, code = normalize_volume(risk_amount / loss_per_lot, spec)
        if code:
            plan.validation_codes.append(code)
            return plan

        actual_loss = gateway.calc_profit(
            signal.symbol, int(signal.direction), lot, signal.preferred_entry, signal.stop_loss
        )
        if actual_loss is None:
            plan.validation_codes.append("CALC_PROFIT_UNAVAILABLE")
            return plan
        actual_loss = abs(actual_loss)

        # Rounding may only ever move risk DOWN, within a small tolerance.
        if actual_loss > risk_amount * cfg.risk.rounding_tolerance:
            plan.validation_codes.append(
                f"NORMALIZED_VOLUME_EXCEEDS_RISK({actual_loss:.2f}>{risk_amount:.2f})"
            )
            return plan

        margin = gateway.calc_margin(
            signal.symbol, int(signal.direction), lot, signal.preferred_entry
        )
        if margin is None:
            plan.validation_codes.append("CALC_MARGIN_UNAVAILABLE")
            return plan
        if margin > account.margin_free:
            plan.validation_codes.append("INSUFFICIENT_FREE_MARGIN")
            return plan

        # Aggregate exposure, measured against what this app already holds.
        actual_risk_pct = actual_loss / equity * 100.0
        exposure = self._portfolio.summarise(signal.symbol, own_positions, specs, equity)
        allowed, reason = self._portfolio.allows(
            exposure,
            actual_risk_pct,
            cfg.risk.max_open_risk_pct,
            cfg.risk.max_currency_risk_pct,
            cfg.risk.max_asset_class_risk_pct,
        )
        if not allowed:
            plan.validation_codes.append(reason)
            return plan

        tick = gateway.tick(signal.symbol)

        plan.plan_id = f"{signal.signal_id}_PLAN"
        plan.direction = signal.direction
        plan.entry = signal.preferred_entry
        plan.stop_loss = signal.stop_loss
        plan.take_profit = signal.take_profit
        plan.risk_percent = risk_pct
        plan.risk_amount = risk_amount
        plan.actual_risk_amount = actual_loss
        plan.lot_size = lot
        plan.margin_required = margin
        plan.created_at = now
        plan.expires_at = now + cfg.execution.preview_ttl_seconds
        plan.max_drift_points = cfg.execution.max_drift_points
        plan.minimum_rr = cfg.risk.minimum_risk_reward
        plan.preview_bid = tick.bid if tick else 0.0
        plan.preview_ask = tick.ask if tick else 0.0
        plan.valid = True
        return plan

    def exposure(
        self,
        symbol: str,
        own_positions: list[PositionInfo],
        specs: dict[str, SymbolSpec],
        equity: float,
    ):
        return self._portfolio.summarise(symbol, own_positions, specs, equity)
