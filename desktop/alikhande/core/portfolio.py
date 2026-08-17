"""Aggregate exposure.

v1.1.0 checked risk per trade and exposure per symbol, and stopped there. That
misses the way a scanner actually goes wrong: EURUSD long, GBPUSD long and
XAUUSD long are not three independent 0.25% bets, they are one ~0.75% bet that
the dollar weakens. This module measures the aggregate.

A breach BLOCKS the new trade. It never silently resizes it: a position the
operator did not ask for is its own kind of surprise, and a blocked trade with a
stated reason is information whereas a shrunken one is noise.
"""

from __future__ import annotations

from .models import ExposureSummary, PositionInfo, SymbolSpec, asset_class_of, currency_legs


def position_risk(
    position: PositionInfo, spec: SymbolSpec | None
) -> tuple[float, bool]:
    """Defined risk of one open position, in account currency.

    Returns ``(risk, bounded)``. The second element is not a courtesy.

    A position with no stop, or one whose symbol cannot be priced, has no
    computable worst case — and a position with no computable worst case is not
    a position with zero risk. Returning ``0.0`` and moving on (which v1.3's
    predecessor did) makes an unbounded position read as *free* to every
    downstream cap, which is the most dangerous way a risk limit can fail: the
    more exposed the account actually is, the more room the caps appear to have.
    """
    if position.stop_loss <= 0.0:
        return 0.0, False
    if spec is None or spec.tick_size <= 0.0 or spec.tick_value <= 0.0:
        return 0.0, False
    distance = abs(position.price_open - position.stop_loss)
    return distance / spec.tick_size * spec.tick_value * position.volume, True


class PortfolioRisk:
    """Totals this app's own exposure and decides whether more may be added."""

    def summarise(
        self,
        candidate_symbol: str,
        positions: list[PositionInfo],
        specs: dict[str, SymbolSpec],
        equity: float,
    ) -> ExposureSummary:
        """Walk open positions and total exposure.

        ``positions`` must already be magic-filtered by the caller: the scanner
        may only be held accountable for what it opened. Positions belonging to
        other software or opened by hand are somebody else's risk budget.
        """
        out = ExposureSummary()
        if equity <= 0.0:
            return out

        candidate_base, candidate_quote = currency_legs(candidate_symbol)
        candidate_class = asset_class_of(candidate_symbol)

        total = symbol_risk = base_risk = quote_risk = class_risk = 0.0

        for position in positions:
            risk, bounded = position_risk(position, specs.get(position.symbol))
            out.open_positions += 1
            if not bounded:
                out.unbounded_positions += 1
                out.unbounded_symbols.append(position.symbol)
            total += risk

            if position.symbol == candidate_symbol:
                symbol_risk += risk

            base, quote = currency_legs(position.symbol)
            if candidate_base and candidate_base in (base, quote):
                base_risk += risk
            if candidate_quote and candidate_quote in (base, quote):
                quote_risk += risk

            if asset_class_of(position.symbol) == candidate_class:
                class_risk += risk

        out.open_risk_pct = total / equity * 100.0
        out.symbol_risk_pct = symbol_risk / equity * 100.0
        out.asset_class_risk_pct = class_risk / equity * 100.0

        # The binding constraint is whichever leg is more concentrated.
        if base_risk >= quote_risk:
            out.currency_risk_pct = base_risk / equity * 100.0
            out.dominant_currency = candidate_base
        else:
            out.currency_risk_pct = quote_risk / equity * 100.0
            out.dominant_currency = candidate_quote

        return out

    def allows(
        self,
        exposure: ExposureSummary,
        new_risk_pct: float,
        max_open_pct: float,
        max_currency_pct: float,
        max_class_pct: float,
    ) -> tuple[bool, str]:
        """Returns ``(allowed, reason)``; ``reason`` names the first breach."""

        # Checked before every cap. With an unbounded position open, every
        # percentage below is a lower bound on true exposure, so comparing them
        # against a limit is meaningless — the limit would pass precisely
        # because the dangerous position is invisible to it.
        if exposure.unbounded_positions > 0:
            symbols = ";".join(exposure.unbounded_symbols)
            return False, (
                f"UNBOUNDED_RISK {exposure.unbounded_positions} position(s) "
                f"without a computable worst case: {symbols}"
            )

        if exposure.open_risk_pct + new_risk_pct > max_open_pct:
            return False, (
                f"OPEN_RISK {exposure.open_risk_pct:.2f}%+{new_risk_pct:.2f}% "
                f"> {max_open_pct:.2f}%"
            )
        if exposure.currency_risk_pct + new_risk_pct > max_currency_pct:
            leg = exposure.dominant_currency or "CURRENCY"
            return False, (
                f"{leg}_EXPOSURE {exposure.currency_risk_pct:.2f}%+{new_risk_pct:.2f}% "
                f"> {max_currency_pct:.2f}%"
            )
        if exposure.asset_class_risk_pct + new_risk_pct > max_class_pct:
            return False, (
                f"ASSET_CLASS {exposure.asset_class_risk_pct:.2f}%+{new_risk_pct:.2f}% "
                f"> {max_class_pct:.2f}%"
            )
        return True, ""
