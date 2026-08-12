"""Presets: Default, Auto and Manual.

Three ways to arrive at an :class:`~alikhande.config.AppConfig`, and one rule
that governs all three: **a preset can tighten, never loosen past a policy
floor.** The floors are the values that make this system refuse trades rather
than resize them, and a settings screen that can dial them down is not a
settings screen, it is a way to disable the safety layer one spinbox at a time.

``DEFAULT``
    The shipped values, untouched. Every one is marked ``[ASSUMED]`` or
    ``[POLICY]`` in the assumption registry, and none has been validated
    against a real broker. Default is not "the right settings" — it is the
    honest starting point, and the Health tab says so.

``AUTO``
    Starts from Default and tightens where the *measured* record justifies it.
    Nothing here is clever: if the recorded expectancy over a meaningful sample
    is negative, the scanner becomes more selective. It has no mechanism for
    becoming less selective, which is the property worth having — an adaptive
    system that can relax its own thresholds will eventually relax them all the
    way down in response to a good run.

``MANUAL``
    The operator's values, persisted. Clamped to the same floors.

## Why Auto adapts on expectancy rather than win rate

Win rate cannot tell you whether a threshold is too loose. A change that admits
more marginal setups can raise the win rate — marginal setups near a zone often
scratch out small wins — while lowering expectancy, because it also admits the
ones that lose a full R. Expectancy in R is the quantity that moves in the
right direction, so it is the one Auto reads.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .config import AppConfig, ScoringConfig, RiskConfig, StatisticsConfig

# Below this many resolved trades, Auto does nothing at all. Adapting a
# threshold on twenty results is not adaptation, it is noise with a feedback
# loop attached.
AUTO_MINIMUM_SAMPLE = 50

# The most Auto may add to the rule-score threshold. Bounded so a bad patch of
# results cannot ratchet the scanner up to a threshold nothing ever clears,
# which would look identical to the app being broken.
AUTO_MAX_TIGHTENING = 10.0


class Profile(str, Enum):
    DEFAULT = "default"
    AUTO = "auto"
    MANUAL = "manual"

    @classmethod
    def parse(cls, value: str | None) -> "Profile":
        """Never raises. The value comes from a JSON file a user can edit."""
        try:
            return cls(str(value).lower())
        except ValueError:
            return cls.DEFAULT


@dataclass(frozen=True)
class Overrides:
    """What Manual mode is allowed to change.

    A deliberately short list. Everything else in ``AppConfig`` is either
    structural (zone geometry, timeframes) or a safety mechanism, and exposing
    those to a settings screen turns every future bug report into an
    archaeology exercise over a preferences file.
    """

    score_threshold: float = ScoringConfig.score_threshold
    minimum_risk_reward: float = RiskConfig.minimum_risk_reward
    risk_percent: float = RiskConfig.risk_percent
    min_outcome_sample: int = StatisticsConfig.min_outcome_sample

    def to_dict(self) -> dict:
        return {
            "score_threshold": self.score_threshold,
            "minimum_risk_reward": self.minimum_risk_reward,
            "risk_percent": self.risk_percent,
            "min_outcome_sample": self.min_outcome_sample,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "Overrides":
        """Tolerant by design: a missing or malformed field falls back to its
        default rather than stopping the application starting."""
        data = data or {}
        base = cls()

        def number(key: str, fallback: float) -> float:
            try:
                return float(data[key])
            except (KeyError, TypeError, ValueError):
                return fallback

        def integer(key: str, fallback: int) -> int:
            try:
                return int(data[key])
            except (KeyError, TypeError, ValueError):
                return fallback

        return cls(
            score_threshold=number("score_threshold", base.score_threshold),
            minimum_risk_reward=number("minimum_risk_reward", base.minimum_risk_reward),
            risk_percent=number("risk_percent", base.risk_percent),
            min_outcome_sample=integer("min_outcome_sample", base.min_outcome_sample),
        )


def clamp(overrides: Overrides, base: AppConfig | None = None) -> Overrides:
    """Force an override set inside the policy floors.

    Applied to whatever Manual mode produces, including values loaded from a
    preferences file that was edited by hand. The clamp is the enforcement
    point; the spinbox ranges in the settings view are only a courtesy.
    """
    base = base or AppConfig()
    return Overrides(
        # A threshold below 50 admits nearly everything the engine scores;
        # above 100 admits nothing, since scores are on a 0–100 scale.
        score_threshold=min(100.0, max(50.0, overrides.score_threshold)),
        # [POLICY] floor. Raising it is the operator's business; lowering it is
        # not available at any preset.
        minimum_risk_reward=max(
            RiskConfig.minimum_risk_reward, overrides.minimum_risk_reward
        ),
        # [POLICY] ceiling, and a floor at a hundredth of a percent so a typo
        # cannot produce a zero-size plan that silently never trades.
        risk_percent=min(
            base.risk.maximum_risk_percent, max(0.01, overrides.risk_percent)
        ),
        # [POLICY] floor. This is the guard that stops a win rate being quoted
        # off nine trades, so it can be raised and never lowered.
        min_outcome_sample=max(
            StatisticsConfig.min_outcome_sample, int(overrides.min_outcome_sample)
        ),
    )


def auto_overrides(summary: dict | None) -> Overrides:
    """Derive Auto's settings from the measured outcome record.

    ``summary`` is what ``Repositories.outcome_summary`` returns. ``None`` or a
    thin sample yields the defaults — Auto's opinion on no evidence is the same
    as Default's, which is the correct opinion to hold on no evidence.
    """
    base = Overrides()
    if not summary:
        return base

    total = int(summary.get("total", 0) or 0)
    if total < AUTO_MINIMUM_SAMPLE:
        return base

    average_r = float(summary.get("avg_r", 0.0) or 0.0)
    if average_r >= 0.15:
        # Comfortably positive. Auto has nothing to add, and the temptation to
        # "capitalise" by loosening is exactly what it must not do.
        return base

    if average_r < 0.0:
        tightening = AUTO_MAX_TIGHTENING
        reward_risk = max(base.minimum_risk_reward, 2.5)
    else:
        # Positive but thin. Half the tightening, RR left alone.
        tightening = AUTO_MAX_TIGHTENING / 2.0
        reward_risk = base.minimum_risk_reward

    return Overrides(
        score_threshold=base.score_threshold + tightening,
        minimum_risk_reward=reward_risk,
        risk_percent=base.risk_percent,
        min_outcome_sample=base.min_outcome_sample,
    )


def resolve(
    profile: Profile,
    manual: Overrides | None = None,
    summary: dict | None = None,
) -> Overrides:
    """The override set a given preset produces, already clamped."""
    if profile is Profile.AUTO:
        return clamp(auto_overrides(summary))
    if profile is Profile.MANUAL:
        return clamp(manual or Overrides())
    return clamp(Overrides())


def configure(
    base: AppConfig,
    profile: Profile,
    manual: Overrides | None = None,
    summary: dict | None = None,
) -> AppConfig:
    """Return ``base`` with the preset's values applied.

    ``base`` is carried through rather than rebuilt so a caller that already
    set symbols — the CLI does — does not lose them to the preset.
    """
    values = resolve(profile, manual, summary)
    return replace(
        base,
        scoring=replace(base.scoring, score_threshold=values.score_threshold),
        risk=replace(
            base.risk,
            minimum_risk_reward=values.minimum_risk_reward,
            risk_percent=values.risk_percent,
        ),
        statistics=replace(
            base.statistics, min_outcome_sample=values.min_outcome_sample
        ),
    )


def describe(profile: Profile) -> str:
    """The translation key for this preset's explanatory paragraph."""
    return f"set.profile.{profile.value}.body"
