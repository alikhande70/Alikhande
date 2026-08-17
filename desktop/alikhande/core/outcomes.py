"""Tracks an ACTIVE signal to its TP or SL and scores the result.

**This closes the loop the MQL5 build left open.** There,
``Repositories::SaveOutcome`` was defined and called by nothing: the ``outcomes``
table was never written, ``OutcomeCounts`` always returned zero,
``has_historical_estimate`` was permanently false, and every probability
rendered "n/a". The Wilson interval, the minimum-sample gate and the
rule-version scoping were all correct and all inert. The infrastructure for
evidence existed; the evidence did not.

The reason it stayed open is structural rather than lazy: in MQL5 the only way
to watch a position tick-by-tick was to be inside the terminal's event loop, and
the outcome depends on the *path* price took, not just where it ended. Here the
same tracker serves a live session and a backtest, because both hand it bars.

What is recorded per signal:

``realized_r``
    Result in R multiples — profit or loss divided by the initial risk distance.
    R rather than currency, because R is comparable across symbols and account
    sizes, and currency is not.

``mfe_r`` / ``mae_r``
    Maximum favourable and adverse excursion, in R. These are what tell you
    whether a stop was badly placed or a target was too greedy — a trade that
    reached +1.8R before stopping out is a different lesson from one that never
    moved.

The conservative rule when a single bar spans both the stop and the target: the
**stop is assumed to have been hit first**. Without tick data there is no way to
know the order, and assuming the favourable one inflates every backtest that
contains a volatile bar. This is the single most common way a backtest lies, and
it is worth the pessimism.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import Direction, SignalState
from .models import Bar, Outcome, SignalCandidate


@dataclass
class TrackedSignal:
    """A signal being watched from entry to resolution."""

    signal_id: str
    symbol: str
    direction: Direction
    entry: float
    stop_loss: float
    take_profit: float
    opened_at: int
    rule_version: str
    scoring_version: str
    parameter_hash: str
    broker_spec_hash: str
    setup: int
    # Excursions in price terms; converted to R on resolution.
    best_price: float = 0.0
    worst_price: float = 0.0
    bars_held: int = 0

    @property
    def risk_distance(self) -> float:
        return abs(self.entry - self.stop_loss)

    def __post_init__(self) -> None:
        self.best_price = self.entry
        self.worst_price = self.entry


@dataclass
class OutcomeTracker:
    """Watches open signals and emits an ``Outcome`` when each resolves."""

    tracked: dict[str, TrackedSignal] = field(default_factory=dict)

    def open(self, candidate: SignalCandidate, entry: float, now: int) -> bool:
        """Begin tracking a signal that has become ACTIVE.

        Refuses a signal with no usable risk distance: an outcome measured in R
        is meaningless when R is zero, and recording it anyway would put a
        divide-by-zero artefact into the evidence base.
        """
        if candidate.signal_id in self.tracked:
            return False
        if candidate.direction == Direction.NONE:
            return False
        if abs(entry - candidate.stop_loss) <= 0.0:
            return False

        self.tracked[candidate.signal_id] = TrackedSignal(
            signal_id=candidate.signal_id,
            symbol=candidate.symbol,
            direction=candidate.direction,
            entry=entry,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            opened_at=now,
            rule_version=candidate.rule_version,
            scoring_version=candidate.scoring_version,
            parameter_hash=candidate.parameter_hash,
            broker_spec_hash=candidate.broker_spec_hash,
            setup=int(candidate.setup),
        )
        return True

    def is_tracking(self, signal_id: str) -> bool:
        return signal_id in self.tracked

    def update(self, symbol: str, bar: Bar, now: int) -> list[tuple[Outcome, SignalState]]:
        """Advance every signal on ``symbol`` by one bar.

        Returns the outcomes that resolved on this bar, each paired with the
        terminal ``SignalState`` the lifecycle should move to.
        """
        resolved: list[tuple[Outcome, SignalState]] = []

        for signal_id in list(self.tracked):
            tracked = self.tracked[signal_id]
            if tracked.symbol != symbol:
                continue

            tracked.bars_held += 1
            if tracked.direction == Direction.LONG:
                tracked.best_price = max(tracked.best_price, bar.high)
                tracked.worst_price = min(tracked.worst_price, bar.low)
                hit_stop = bar.low <= tracked.stop_loss
                hit_target = tracked.take_profit > 0.0 and bar.high >= tracked.take_profit
            else:
                tracked.best_price = min(tracked.best_price, bar.low)
                tracked.worst_price = max(tracked.worst_price, bar.high)
                hit_stop = bar.high >= tracked.stop_loss
                hit_target = tracked.take_profit > 0.0 and bar.low <= tracked.take_profit

            if not hit_stop and not hit_target:
                continue

            # Both touched inside one bar: assume the stop went first. Without
            # tick data the order is unknowable, and assuming the favourable one
            # is how a backtest flatters itself.
            if hit_stop:
                exit_price = tracked.stop_loss
                state = SignalState.SL
                result = "SL"
            else:
                exit_price = tracked.take_profit
                state = SignalState.TP
                result = "TP"

            resolved.append((self._score(tracked, exit_price, result, now), state))
            del self.tracked[signal_id]

        return resolved

    def expire(self, signal_id: str, price: float, now: int) -> Outcome | None:
        """Close a tracked signal that ran out of time rather than resolving.

        Recorded as EXPIRED, which ``lifecycle.is_scorable`` deliberately
        excludes from win-rate maths: expiry says something about the scanner,
        not about the setup's edge.
        """
        tracked = self.tracked.pop(signal_id, None)
        if tracked is None:
            return None
        return self._score(tracked, price, "EXPIRED", now)

    def _score(self, tracked: TrackedSignal, exit_price: float, result: str, now: int) -> Outcome:
        risk = tracked.risk_distance
        sign = 1.0 if tracked.direction == Direction.LONG else -1.0

        realized_r = (exit_price - tracked.entry) * sign / risk
        mfe_r = (tracked.best_price - tracked.entry) * sign / risk
        mae_r = (tracked.worst_price - tracked.entry) * sign / risk

        return Outcome(
            signal_id=tracked.signal_id,
            result=result,
            realized_r=realized_r,
            # MFE is favourable by definition and MAE adverse; clamping stops a
            # gap through the entry from producing a "favourable" negative.
            mfe_r=max(0.0, mfe_r),
            mae_r=min(0.0, mae_r),
            closed_at=now,
            source="REPLAY",
            evidence_quality="BAR_CONSERVATIVE",
            entry_price=tracked.entry,
            exit_price=exit_price,
            valid_for_statistics=result in ("TP", "SL"),
            rule_version=tracked.rule_version,
            scoring_version=tracked.scoring_version,
            parameter_hash=tracked.parameter_hash,
            broker_spec_hash=tracked.broker_spec_hash,
        )
