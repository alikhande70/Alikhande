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
    __slots__ = ("ok", "request", "retcode", "reason")

    def __init__(
        self,
        ok: bool,
        request: OrderRequest | None = None,
        retcode: int = 0,
        reason: str = "",
    ) -> None:
        self.ok = ok
        self.request = request
        self.retcode = retcode
        self.reason = reason


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

        codes = self._guards.trade_permissions(account, spec)
        if codes:
            return PreflightResult(False, reason=";".join(codes))

        codes = self._guards.stops_valid(plan, spec)
        if codes:
            return PreflightResult(False, reason=";".join(codes))

        assert spec is not None  # trade_permissions already refused a missing spec

        tick = gateway.tick(plan.symbol)
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

        request = OrderRequest(
            symbol=plan.symbol,
            direction=plan.direction,
            volume=plan.lot_size,
            price=current,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            deviation=max(1, int(plan.max_drift_points)),
            magic=cfg.execution.magic,
            comment=cfg.execution.order_comment,
        )

        accepted, retcode, comment = gateway.check_order(request)
        if not accepted:
            return PreflightResult(
                False, retcode=retcode, reason=f"ORDER_CHECK_FAILED({retcode}:{comment})"
            )

        return PreflightResult(True, request=request, retcode=retcode)
