"""Rolling spread sample per symbol.

Classification is relative to the symbol's own median rather than an absolute
point threshold, because "30 points" means something completely different on
XAUUSD than on EURUSD. The percentile is exposed as well — the regime engine
wants the distributional position, not just the bucket.
"""

from __future__ import annotations

from collections import deque

from ..config import ScanConfig
from .enums import SpreadState
from .indicators import median


class SpreadTracker:
    def __init__(self, scan: ScanConfig | None = None) -> None:
        self._scan = scan or ScanConfig()
        self._samples: deque[float] = deque(maxlen=self._scan.spread_sample_capacity)

    @property
    def count(self) -> int:
        return len(self._samples)

    def add(self, value: float) -> None:
        if value <= 0.0:
            return
        self._samples.append(value)

    def median(self) -> float:
        return median(list(self._samples))

    def percentile(self, value: float) -> float:
        """Fraction of observed samples at or below ``value``, in 0..1."""
        if not self._samples:
            return 0.5
        below = sum(1 for sample in self._samples if sample <= value)
        return below / len(self._samples)

    def classify(self, current: float) -> tuple[SpreadState, float, float]:
        """Classify ``current`` against the sample.

        Returns ``(state, ratio, percentile)``. Ratio and percentile are zero
        while warming up, so a caller can never mistake an unwarmed tracker for
        a normal spread — the same reasoning as the tri-state news gate, one
        layer down.
        """
        cfg = self._scan
        if len(self._samples) < cfg.spread_warmup_samples:
            return SpreadState.WARMING_UP, 0.0, 0.0

        reference = self.median()
        if reference <= 0.0:
            return SpreadState.WARMING_UP, 0.0, 0.0

        ratio = current / reference
        percentile = self.percentile(current)

        if ratio < cfg.spread_normal_max_ratio:
            return SpreadState.NORMAL, ratio, percentile
        if ratio < cfg.spread_elevated_max_ratio:
            return SpreadState.ELEVATED, ratio, percentile
        if ratio < cfg.spread_high_max_ratio:
            return SpreadState.HIGH, ratio, percentile
        return SpreadState.EXTREME, ratio, percentile
