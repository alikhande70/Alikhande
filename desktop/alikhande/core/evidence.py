"""Turns outcomes into a number an operator can act on — or refuses to.

This module exists because of one request and one constraint that pull against
each other. The request: *show me, per symbol, the percentage chance a buy or a
sell works out.* The constraint, which has governed this project since v1.1.0:
**a rule score is not a probability, and a probability from a handful of trades
is not evidence.**

Both are satisfiable, but only by saying out loud which one you are looking at.
So every number this module produces arrives with a tier attached, and the tier
is not decoration — it changes what is displayed and how the list is ordered.

## Three tiers

``MEASURED`` (n ≥ 30)
    Enough resolved trades for a Wilson interval to be worth reading. A win
    percentage is shown, with its interval and sample size beside it.

``PROVISIONAL`` (8 ≤ n < 30)
    Something is there, but the interval is so wide it would be read as
    precision it does not have. The interval is shown; **no headline
    percentage is**, because a big "67%" over n=9 is a lie told with true
    numbers.

``UNMEASURED`` (n < 8)
    No claim at all. The rule score is shown instead, labelled as a rule score.

## Why the conservative bound, not the point estimate

Ranking is by expectancy computed from the **Wilson lower bound**, not from
wins/total. The difference matters: 65% over n=31 and 60% over n=200 have
similar point estimates, but the second is far better established, and the
lower bound is what encodes that. Ranking on the point estimate systematically
promotes whichever symbol happens to have the smallest sample — the exact
opposite of what an evidence-weighted list should do.

## Why expectancy is the ranking key rather than win rate

Win rate alone cannot tell you whether to take a trade. 70% at 0.5R is a losing
system; 40% at 3R is a good one. The quantity that decides it is expectancy per
trade, in R:

    E[R] = p · RR − (1 − p)

which is positive exactly when ``p > 1 / (1 + RR)``. That break-even rate is
reported alongside, because "you need 29% and you are measuring 62%" is a
sentence an operator can check, and "62%" on its own is not.

## Provenance is part of the claim

An outcome from a synthetic replay and an outcome from a demo account are both
real records of something, but they are not evidence about the same thing.
They are counted separately and the source is displayed. A win rate whose
provenance is hidden is how a backtest ends up quoted as live performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from .statistics import wilson


class EvidenceTier(IntEnum):
    """How much a displayed number is allowed to claim.

    Ordered so a plain ``>`` comparison means "better established", which is
    what makes the tier usable as the primary sort key.
    """

    UNMEASURED = 0
    PROVISIONAL = 1
    MEASURED = 2


class Provenance(IntEnum):
    """Where the outcomes behind a number came from.

    ``MIXED`` is deliberately its own value rather than being collapsed into
    ``LIVE``. A sample that is 90% replay and 10% demo is not a demo result,
    and labelling it one would be the single most misleading thing this module
    could do.
    """

    NONE = 0
    REPLAY = 1
    LIVE = 2
    MIXED = 3


# Below this, nothing is said at all. Above it but below the statistics
# config's ``min_outcome_sample``, only an interval is shown.
PROVISIONAL_SAMPLE = 8


def breakeven_win_rate(reward_risk: float) -> float:
    """The win rate at which a system with this RR neither makes nor loses.

    Returns 1.0 for a non-positive RR: a trade with no reward needs a
    certainty it cannot have, which is the correct answer rather than an
    error.
    """
    if reward_risk <= 0.0:
        return 1.0
    return 1.0 / (1.0 + reward_risk)


def expectancy_r(win_rate: float, reward_risk: float) -> float:
    """Expected result per trade in R.

    Assumes the loss case is exactly −1R, which is true by construction here:
    R *is* the distance to the stop, and position size is derived from it.
    """
    return win_rate * reward_risk - (1.0 - win_rate)


@dataclass(frozen=True)
class Evidence:
    """Everything known about how a setup has actually performed.

    Frozen because it is derived, handed to the UI thread, and read from
    several views. A mutable version invites one view to "fix up" a field and
    another to render the fixed-up value as measurement.
    """

    tier: EvidenceTier = EvidenceTier.UNMEASURED
    provenance: Provenance = Provenance.NONE
    wins: int = 0
    total: int = 0
    reward_risk: float = 0.0

    point: float = 0.0  # wins / total
    low: float = 0.0  # Wilson lower bound
    high: float = 0.0  # Wilson upper bound

    # Expectancy from the lower bound and from the point estimate. Two numbers
    # rather than one because the gap between them *is* the uncertainty, and
    # collapsing it to a single figure hides exactly what the operator needs.
    expectancy_low_r: float = 0.0
    expectancy_point_r: float = 0.0

    rule_score: float = 0.0
    score_threshold: float = 0.0

    @property
    def has_rate(self) -> bool:
        """Whether a win percentage may be displayed as a headline figure."""
        return self.tier == EvidenceTier.MEASURED

    @property
    def breakeven(self) -> float:
        return breakeven_win_rate(self.reward_risk)

    @property
    def clears_breakeven(self) -> bool:
        """True only when the *conservative* bound clears break-even.

        Using ``low`` rather than ``point`` is the whole discipline of this
        module in one property: the claim is "even on the pessimistic reading
        of this sample, the setup pays", which is a claim worth acting on.
        """
        return self.tier == EvidenceTier.MEASURED and self.low > self.breakeven

    @property
    def rank_key(self) -> tuple[int, float, float]:
        """Sort key, best first when sorted in reverse.

        Tier leads. A measured 58% outranks an unmeasured 95 rule score, and
        that ordering is the point: the list is sorted by what is *known*, not
        by what is hoped. Within a tier, conservative expectancy decides; rule
        score breaks the remaining ties and orders the unmeasured block, where
        it is the only signal available.
        """
        return (int(self.tier), self.expectancy_low_r, self.rule_score)


def assess(
    *,
    wins: int,
    total: int,
    reward_risk: float,
    rule_score: float,
    score_threshold: float,
    provenance: Provenance = Provenance.NONE,
    min_sample: int = 30,
    z: float = 1.96,
) -> Evidence:
    """Build an :class:`Evidence` from raw counts.

    Kept as a free function taking primitives so it can be tested without a
    database, a config object or a candidate — the arithmetic here is the part
    most worth testing directly.
    """
    base = Evidence(
        wins=max(0, wins),
        total=max(0, total),
        reward_risk=max(0.0, reward_risk),
        rule_score=rule_score,
        score_threshold=score_threshold,
        provenance=provenance if total > 0 else Provenance.NONE,
    )

    if base.total <= 0 or base.wins > base.total:
        return base

    interval = wilson(base.wins, base.total, z)
    if interval is None:
        return base

    low, high = interval
    point = base.wins / base.total

    if base.total >= min_sample:
        tier = EvidenceTier.MEASURED
    elif base.total >= PROVISIONAL_SAMPLE:
        tier = EvidenceTier.PROVISIONAL
    else:
        # Counts exist but are too few to say anything. The interval is still
        # computed and carried, because the Signal view shows it as "what we
        # have so far" — it is the *headline* that is withheld, not the data.
        tier = EvidenceTier.UNMEASURED

    return Evidence(
        tier=tier,
        provenance=base.provenance,
        wins=base.wins,
        total=base.total,
        reward_risk=base.reward_risk,
        point=point,
        low=low,
        high=high,
        expectancy_low_r=expectancy_r(low, base.reward_risk),
        expectancy_point_r=expectancy_r(point, base.reward_risk),
        rule_score=rule_score,
        score_threshold=score_threshold,
    )


def provenance_of(kinds: set[str]) -> Provenance:
    """Collapse a set of run-kind names into a single provenance label.

    ``kinds`` holds ``RuntimeKind`` member names as persisted on the ``runs``
    row. Unknown names are ignored rather than guessed at; a name this build
    does not recognise came from a different build, and inventing a category
    for it would put unlabelled data into a labelled field.
    """
    live = "LIVE" in kinds
    replay = "REPLAY" in kinds or "OFFLINE" in kinds
    if live and replay:
        return Provenance.MIXED
    if live:
        return Provenance.LIVE
    if replay:
        return Provenance.REPLAY
    return Provenance.NONE


@dataclass
class Opportunity:
    """One row of the scanner: a symbol, a direction, and what backs it.

    This is the object the landing screen ranks. It is assembled in the app
    layer from a ``SymbolView`` and an :class:`Evidence`, and carries no Qt and
    no gateway — the scanner list is sortable and testable without a UI.
    """

    symbol: str = ""
    direction: int = 0  # Direction, as an int to keep this module import-light
    setup: int = 0
    evidence: Evidence = field(default_factory=Evidence)

    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reward_risk: float = 0.0
    digits: int = 5

    tradable: bool = False  # passed every gate; a plan exists
    blocked_reason: str = ""  # the first gate that said no, for display
    headline: str = ""  # the one-line "why", already localised by the caller

    @property
    def rank_key(self) -> tuple[int, int, float, float]:
        """Tradable first, then the evidence ordering.

        A blocked setup can still be worth looking at — that is why it stays in
        the list at all — but it must never sit above something actionable.
        """
        tier, expectancy, score = self.evidence.rank_key
        return (1 if self.tradable else 0, tier, expectancy, score)
