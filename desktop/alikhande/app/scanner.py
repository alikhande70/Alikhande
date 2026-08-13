"""Builds the ranked opportunity list the landing screen shows.

The window used to open on a dashboard: a set of panels describing the state of
the system, from which the operator worked out where to look. This inverts that.
The first thing on screen is now an ordered answer to the only question worth
asking on launch — *which of these is worth my attention right now, and how
sure are we?* — and everything else is somewhere to go and check it.

Deliberately outside ``ui/``. Ranking is a decision, not a rendering, and a
decision that lives in a widget cannot be tested without a display server. The
whole ordering is exercised by unit tests that never import Qt.

Deliberately outside ``core/`` too: it reads a repository. Core imports nothing
external, and that property is worth more than the tidiness of having this file
next to the evidence maths it uses.
"""

from __future__ import annotations

from ..config import AppConfig
from ..core.enums import Direction
from ..core.evidence import Evidence, Opportunity, assess, provenance_of
from .engine import EngineSnapshot, SymbolView


def _reward_risk(entry: float, stop: float, target: float) -> float:
    """RR from the three prices, or 0 when the geometry is degenerate.

    Returns 0 rather than raising or clamping: a plan whose risk distance is
    zero is not a low-RR plan, it is a broken one, and the caller renders it as
    "no RR" rather than as "RR 0.0", which would read as a real measurement.
    """
    risk = abs(entry - stop)
    if risk <= 0.0 or target <= 0.0:
        return 0.0
    return abs(target - entry) / risk


def evidence_for(
    view: SymbolView,
    config: AppConfig,
    repositories=None,
    *,
    reward_risk: float = 0.0,
) -> Evidence:
    """Look up what this symbol's setup has actually done before.

    ``repositories`` may be ``None`` (offline exploration, or a test), in which
    case the result is an honest ``UNMEASURED`` carrying only the rule score.
    That is the same shape the UI renders on a fresh install, so the empty path
    is the well-tested one rather than an afterthought.
    """
    signal = view.signal
    score = 0.0
    if signal is not None:
        score = max(signal.long_score, signal.short_score)

    wins = total = 0
    kinds: set[str] = set()
    if repositories is not None and signal is not None and int(signal.setup) != 0:
        getter = getattr(repositories, "outcome_provenance", None)
        if getter is not None:
            wins, total, kinds = getter(
                signal.symbol, int(signal.setup), signal.rule_version
            )

    return assess(
        wins=wins,
        total=total,
        reward_risk=reward_risk,
        rule_score=score,
        score_threshold=config.scoring.score_threshold,
        provenance=provenance_of(kinds),
        min_sample=config.statistics.min_outcome_sample,
        z=config.statistics.confidence_z,
    )


def _blocked_reason(view: SymbolView) -> str:
    """The first thing standing between this setup and a tradable plan.

    One reason, not all of them. A row that lists four codes is a row nobody
    reads; the operator wants to know what to fix or wait for, and the first
    blocker is the answer to that. The Signal view shows the full set.
    """
    if not view.resolved:
        return "SYMBOL_UNRESOLVED"
    if view.last_error:
        return "DATA_ERROR"
    if view.news_blocks:
        return "NEWS_WINDOW"

    signal = view.signal
    if signal is None:
        return "NO_STRUCTURE"
    if signal.hard_blocked and signal.validation_codes:
        return signal.validation_codes[0]
    if signal.direction == Direction.NONE:
        return "NO_SETUP"

    plan = view.plan
    if plan is None:
        return "NO_PLAN"
    if not plan.valid:
        return plan.validation_codes[0] if plan.validation_codes else "PLAN_INVALID"
    return ""


def build(
    snapshot: EngineSnapshot,
    config: AppConfig,
    repositories=None,
) -> list[Opportunity]:
    """Rank every scanned symbol, best first.

    Every symbol appears, including the ones with nothing on them. A scanner
    that hides its misses trains the operator to believe it is always finding
    something, and the empty rows are also the ones that show the scan is alive
    and looking at what it claims to be looking at.
    """
    opportunities: list[Opportunity] = []

    for view in snapshot.symbols:
        signal = view.signal
        plan = view.plan

        if plan is not None and plan.valid:
            entry, stop, target = plan.entry, plan.stop_loss, plan.take_profit
        elif signal is not None:
            entry = signal.preferred_entry
            stop, target = signal.stop_loss, signal.take_profit
        else:
            entry = stop = target = 0.0

        rr = _reward_risk(entry, stop, target)
        reason = _blocked_reason(view)

        opportunities.append(
            Opportunity(
                symbol=view.symbol or view.requested,
                direction=int(signal.direction) if signal is not None else 0,
                setup=int(signal.setup) if signal is not None else 0,
                evidence=evidence_for(view, config, repositories, reward_risk=rr),
                entry=entry,
                stop_loss=stop,
                take_profit=target,
                reward_risk=rr,
                digits=view.snapshot.digits or 5,
                # Tradable means the whole pipeline said yes, not that the
                # score was high. The gates are what make the number safe to
                # act on, so passing them is what earns a place at the top.
                tradable=not reason and plan is not None and plan.valid,
                blocked_reason=reason,
            )
        )

    opportunities.sort(key=lambda o: o.rank_key, reverse=True)
    return opportunities


def actionable(opportunities: list[Opportunity]) -> list[Opportunity]:
    """The subset a badge should count: tradable and clearing break-even.

    Note what is excluded — a tradable setup with no measured evidence is not
    counted here even when its rule score is high. The count is meant to read
    as "this many things are backed by numbers", and inflating it with
    unmeasured setups is how a badge becomes background noise.
    """
    return [o for o in opportunities if o.tradable and o.evidence.clears_breakeven]
