"""Everything that must be true immediately before an order is sent.

Note on ``check_order``: MetaQuotes is explicit that a successful order check
does NOT guarantee the order will fill. It screens out requests certain to be
rejected; it says nothing about what the market does next. The result therefore
still has to be reconciled after submission — see ``execution``.

This module is the only place an ``OrderRequest`` is constructed. The execution
engine sends what it is handed and nothing else, so there is exactly one place
where the contents of an order are decided.
"""

from __future__ import annotations

from ..config import AppConfig
from .enums import Direction
from .guards import TradeGuards
from .models import AccountInfo, OrderRequest, SymbolSpec, TradePlan
from .ports import BrokerGateway


class PreflightResult:
    __slots__ = ("ok", "request", "retcode", "reason", "actual_risk_amount")

    def __init__(
        self,
        ok: bool,
        request: OrderRequest | None = None,
        retcode: int = 0,
        reason: str = "",
        actual_risk_amount: float = 0.0,
    ) -> None:
        self.ok = ok
        self.request = request
        self.retcode = retcode
        self.reason = reason
        self.actual_risk_amount = actual_risk_amount


class Preflight:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or AppConfig()
        self._guards = TradeGuards()

    def validate(
        self,
        plan: TradePlan,
        *,
        gateway: BrokerGateway,
        account: AccountInfo | None,
        spec: SymbolSpec | None,
        now: int,
        correlation_comment: str = "",
    ) -> PreflightResult:
        """Build and validate the request.

        On success ``result.request`` is ready to send verbatim; on failure
        ``result.reason`` names the first failed gate.
        """
        cfg = self._config

        if not plan.valid:
            return PreflightResult(False, reason="PLAN_INVALID")
        if now > plan.expires_at:
            return PreflightResult(False, reason="PREVIEW_EXPIRED")

        # Re-read the specification at Confirm, not only when the preview was
        # built. A changed contract size/tick value invalidates the sizing even
        # when price itself has barely moved.
        try:
            current_spec = gateway.symbol_spec(plan.symbol)
        except Exception as error:
            return PreflightResult(
                False, reason=f"BROKER_SPEC_UNAVAILABLE({type(error).__name__})"
            )
        if current_spec is None or not current_spec.ready:
            return PreflightResult(False, reason="BROKER_SPEC_UNAVAILABLE")
        if (
            spec is not None
            and spec.fingerprint
            and current_spec.fingerprint != spec.fingerprint
        ):
            return PreflightResult(False, reason="BROKER_SPEC_CHANGED_REPLAN")
        spec = current_spec

        codes = self._guards.trade_permissions(account, spec)
        if codes:
            return PreflightResult(False, reason=";".join(codes))

        codes = self._guards.stops_valid(plan, spec)
        if codes:
            return PreflightResult(False, reason=";".join(codes))

        assert spec is not None  # trade_permissions already refused a missing spec

        # Exposure is also a last-moment broker read. The scan pass checks this
        # while building the preview, but a position/order can appear during
        # the operator's arming window. API failure is distinct from a real
        # empty list and fails closed.
        try:
            # Any same-symbol exposure is a refusal, not only this EA's magic.
            # On a netting account a manual position would merge with the new
            # order under one position_id and make later exits impossible to
            # attribute without guessing.
            positions = gateway.positions(None)
            orders = gateway.orders(None)
        except Exception as error:
            return PreflightResult(
                False, reason=f"BROKER_EXPOSURE_UNAVAILABLE({type(error).__name__})"
            )
        if self._guards.has_exposure(plan.symbol, positions, orders):
            return PreflightResult(False, reason="ALREADY_EXPOSED")

        try:
            tick = gateway.tick(plan.symbol)
        except Exception as error:
            return PreflightResult(
                False, reason=f"BROKER_TICK_UNAVAILABLE({type(error).__name__})"
            )
        if tick is None:
            return PreflightResult(False, reason="NO_TICK")
        if spec.point <= 0.0:
            return PreflightResult(False, reason="NO_POINT")

        # A tick nobody has updated in a while is not a quote, it is a memory.
        # Sizing and drift both key off it, so staleness is a refusal.
        age = now - tick.time
        if age > cfg.scan.max_tick_age_seconds:
            return PreflightResult(False, reason=f"STALE_TICK({age}s)")

        # The plan was sized against a specific price. If the market has moved
        # beyond tolerance the plan's risk arithmetic no longer describes the
        # trade that would actually open, so it is re-planned rather than sent.
        current = tick.ask if plan.direction == Direction.LONG else tick.bid
        drift_points = abs(current - plan.entry) / spec.point
        if drift_points > plan.max_drift_points:
            return PreflightResult(
                False,
                reason=f"PRICE_DRIFT_EXCEEDED({drift_points:.0f}>{plan.max_drift_points:.0f} pts)",
            )

        # Price drift inside the tolerance can still increase the cash distance
        # to the stop. Reprice the exact volume/request price at the last
        # responsible moment; otherwise a plan that was within budget when
        # previewed can leave with more risk than the operator approved.
        try:
            actual_risk = gateway.calc_profit(
                plan.symbol,
                int(plan.direction),
                plan.lot_size,
                current,
                plan.stop_loss,
            )
        except Exception as error:
            return PreflightResult(
                False, reason=f"ACTUAL_RISK_UNAVAILABLE({type(error).__name__})"
            )
        if actual_risk is None:
            return PreflightResult(False, reason="ACTUAL_RISK_UNAVAILABLE")
        actual_risk = abs(float(actual_risk))
        budget = plan.risk_amount or plan.actual_risk_amount
        if actual_risk <= 0.0 or budget <= 0.0:
            return PreflightResult(False, reason="ACTUAL_RISK_INVALID")
        if actual_risk > budget * cfg.risk.rounding_tolerance:
            return PreflightResult(
                False,
                reason=(
                    "ACTUAL_RISK_EXCEEDS_PLAN"
                    f"({actual_risk:.2f}>{budget:.2f})"
                ),
            )

        request = OrderRequest(
            symbol=plan.symbol,
            direction=plan.direction,
            volume=plan.lot_size,
            price=current,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            deviation=max(1, int(plan.max_drift_points)),
            magic=cfg.execution.magic,
            # The execution identity is broker-visible and persisted before
            # send. A static product comment cannot distinguish two trades on
            # the same symbol after a crash, so execution always supplies the
            # unique value on the real send path. The fallback keeps direct
            # preflight callers and shadow diagnostics useful.
            comment=correlation_comment or cfg.execution.order_comment,
        )

        try:
            accepted, retcode, comment = gateway.check_order(request)
        except Exception as error:
            return PreflightResult(
                False, reason=f"ORDER_CHECK_UNAVAILABLE({type(error).__name__})"
            )
        if not accepted:
            return PreflightResult(
                False, retcode=retcode, reason=f"ORDER_CHECK_FAILED({retcode}:{comment})"
            )

        return PreflightResult(
            True,
            request=request,
            retcode=retcode,
            actual_risk_amount=actual_risk,
        )
