"""Outcome statistics.

The governing rule of this module: a rule score is not a probability, and a
probability computed from a handful of trades is not evidence. Two guards
enforce that:

1. Nothing is reported below ``min_outcome_sample`` observations.
2. Any reported rate is accompanied by a Wilson interval and the sample size,
   and callers render all three or none — which is why ``format_probability``
   exists rather than each call site formatting its own string.

v1.1.0 shipped a correct Wilson implementation that nothing ever called, and a
candidate struct whose ``has_historical_estimate`` flag was hardcoded false.
The maths was right and unreachable.
"""

from __future__ import annotations

import math
from typing import Protocol

from ..config import StatisticsConfig
from .enums import SetupType
from .models import SignalCandidate


class OutcomeCounter(Protocol):
    """The only thing the statistics layer needs from persistence.

    Narrow on purpose: it keeps ``core`` from importing the repository module,
    and it makes the layer trivially testable with a stub.
    """

    def outcome_counts(self, symbol: str, setup: int, rule_version: str) -> tuple[int, int]:
        """Return ``(wins, total)`` for this symbol, setup and rule version."""


def wilson(wins: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval.

    Preferred over the normal approximation because it stays inside [0, 1] and
    stays honest at small ``n`` and at rates near 0 or 1 — exactly the regime a
    young strategy database lives in.

    Returns ``None`` for input that describes nothing, rather than a
    zero-width interval that would read as certainty.
    """
    if total <= 0 or wins < 0 or wins > total:
        return None

    n = float(total)
    p = wins / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


class Statistics:
    def __init__(
        self,
        counter: OutcomeCounter | None = None,
        config: StatisticsConfig | None = None,
    ) -> None:
        self._counter = counter
        self._config = config or StatisticsConfig()

    def enrich(self, candidate: SignalCandidate) -> bool:
        """Populate the historical fields, or leave the estimate flag false.

        Outcomes are scoped to the candidate's own rule version: mixing results
        from before and after a logic change describes a system that never ran.
        """
        candidate.has_historical_estimate = False
        candidate.historical_win_rate = 0.0
        candidate.sample_size = 0
        candidate.confidence_low = 0.0
        candidate.confidence_high = 0.0

        if self._counter is None or candidate.setup == SetupType.NONE:
            return False

        wins, total = self._counter.outcome_counts(
            candidate.symbol, int(candidate.setup), candidate.rule_version
        )
        candidate.sample_size = total
        if total < self._config.min_outcome_sample:
            return False

        interval = wilson(wins, total, self._config.confidence_z)
        if interval is None:
            return False

        candidate.historical_win_rate = wins / total
        candidate.confidence_low, candidate.confidence_high = interval
        candidate.has_historical_estimate = True
        return True

    def format_probability(self, candidate: SignalCandidate) -> str:
        """Centralised so no call site can print a bare percentage without its
        sample size, or print anything at all below the minimum sample."""
        if not candidate.has_historical_estimate:
            return f"n/a ({candidate.sample_size}/{self._config.min_outcome_sample} samples)"
        return (
            f"{candidate.historical_win_rate * 100:.0f}% "
            f"[{candidate.confidence_low * 100:.0f}–{candidate.confidence_high * 100:.0f}] "
            f"n={candidate.sample_size}"
        )
