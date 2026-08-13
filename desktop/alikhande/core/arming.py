"""Two-step arming for demo execution.

Execution requires two distinct human actions separated in time:

1. **ARM** — the operator selects a previewed plan and arms it.
2. **CONFIRM** — the operator confirms the armed plan.

The arming carries a short TTL. If the market moves or the operator hesitates
past it, the intent expires and must be re-armed against a fresh plan. This is
what stops "I armed it a while ago and forgot" turning into an order at a price
nobody evaluated.

A single click cannot execute. Arm and Confirm are separate controls in the UI,
and the confirm is only meaningful while an intent is armed and live.

The desktop build tightens one thing over the EA: confirming re-checks that the
*plan itself* is unchanged, not merely that the ids match. A re-planned signal
keeps its plan id (it is derived from the signal id), so an id comparison alone
would let a plan whose entry, stop or size moved underneath the operator sail
through as "the same plan". It is not the same plan; it is the same slot.
"""

from __future__ import annotations

from ..config import ExecutionConfig
from .journal import Journal
from .models import ArmedIntent, TradePlan


def _plan_shape(plan: TradePlan) -> tuple:
    """The parts of a plan an operator actually evaluates before arming."""
    return (
        plan.plan_id,
        round(plan.entry, 10),
        round(plan.stop_loss, 10),
        round(plan.take_profit, 10),
        round(plan.lot_size, 10),
    )


class IntentArming:
    def __init__(
        self, config: ExecutionConfig | None = None, journal: Journal | None = None
    ) -> None:
        self._config = config or ExecutionConfig()
        self._journal = journal or Journal()
        self._intent = ArmedIntent()
        self._shape: tuple | None = None

    @property
    def current(self) -> ArmedIntent:
        return self._intent

    def is_armed(self, now: int) -> bool:
        return self._intent.armed and now <= self._intent.expires_at

    def seconds_remaining(self, now: int) -> int:
        if not self._intent.armed:
            return 0
        return max(0, self._intent.expires_at - now)

    def sweep(self, now: int) -> bool:
        """Expire a stale intent. Returns True if one was swept.

        Expiry is evaluated lazily on read, but also swept so the UI stops
        showing an armed state that is no longer actionable.
        """
        if not self._intent.armed:
            return False
        if now <= self._intent.expires_at:
            return False
        self._journal.info(
            "INTENT_EXPIRED",
            self._intent.symbol,
            f"armed plan {self._intent.plan_id} expired unconfirmed",
            now,
        )
        self._intent = ArmedIntent()
        self._shape = None
        return True

    def arm(self, plan: TradePlan, now: int) -> bool:
        """Arm a plan, replacing any previous intent.

        Only one plan may be armed at a time — the same single-in-flight
        discipline the execution engine uses, for the same reason: concurrent
        intents cannot be attributed to a click.
        """
        if not plan.valid:
            return False

        ttl = max(5, self._config.arm_ttl_seconds)
        self._intent = ArmedIntent(
            armed=True,
            plan_id=plan.plan_id,
            signal_id=plan.signal_id,
            symbol=plan.symbol,
            entry=plan.entry,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            lot_size=plan.lot_size,
            armed_at=now,
            expires_at=now + ttl,
        )
        self._shape = _plan_shape(plan)
        self._journal.info(
            "INTENT_ARMED",
            plan.symbol,
            f"plan {plan.plan_id} armed for {ttl}s; confirmation required",
            now,
        )
        return True

    def disarm(self, reason: str, now: int) -> None:
        if not self._intent.armed:
            return
        self._journal.info("INTENT_DISARMED", self._intent.symbol, reason, now)
        self._intent = ArmedIntent()
        self._shape = None

    def confirm(self, plan: TradePlan, now: int) -> tuple[bool, str]:
        """Consume the armed intent.

        Returns ``(confirmed, reason)``. False unless an intent is armed, live,
        and refers to the *same plan in the same shape* — so neither a stale
        click nor a silently re-planned signal can fire something the operator
        never evaluated.
        """
        if not self._intent.armed:
            return False, "NO_ARMED_INTENT"

        if now > self._intent.expires_at:
            self.disarm("ARMED_INTENT_EXPIRED", now)
            return False, "ARMED_INTENT_EXPIRED"

        if self._intent.plan_id != plan.plan_id:
            # The armed plan is not the plan now on screen: the signal was
            # re-planned underneath the operator.
            self.disarm("ARMED_PLAN_SUPERSEDED", now)
            return False, "ARMED_PLAN_SUPERSEDED"

        if self._shape != _plan_shape(plan):
            # Same id, different numbers. Refuse rather than execute something
            # the operator did not look at.
            self.disarm("ARMED_PLAN_CHANGED", now)
            return False, "ARMED_PLAN_CHANGED"

        self._intent = ArmedIntent()
        self._shape = None
        return True, ""
