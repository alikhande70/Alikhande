"""Pre-trade permission and distance checks, and account circuit breakers.

The guards here are the cheap, deterministic refusals — answerable from account
and symbol state without asking the trade server. Anything needing the server's
opinion belongs in ``preflight``.
"""

from __future__ import annotations

import time

from ..config import RiskConfig
from .models import AccountInfo, OrderInfo, PositionInfo, RiskState, SymbolSpec, TradePlan

# MetaTrader's SYMBOL_TRADE_MODE values. Named here so the core never has to
# import the MT5 package to know what a mode integer means.
SYMBOL_TRADE_MODE_DISABLED = 0
SYMBOL_TRADE_MODE_LONGONLY = 1
SYMBOL_TRADE_MODE_SHORTONLY = 2
SYMBOL_TRADE_MODE_CLOSEONLY = 3
SYMBOL_TRADE_MODE_FULL = 4


class TradeGuards:
    def has_exposure(
        self, symbol: str, positions: list[PositionInfo], orders: list[OrderInfo]
    ) -> bool:
        """Any position or working order on this symbol from this app.

        Inputs must be magic-filtered by the caller: the scanner must not refuse
        to trade because a human has a manual position open, and must not treat
        somebody else's order as its own.
        """
        if any(p.symbol == symbol for p in positions):
            return True
        return any(o.symbol == symbol for o in orders)

    def has_foreign_exposure(
        self, symbol: str, all_positions: list[PositionInfo], magic: int
    ) -> bool:
        """A position on this symbol from somewhere else.

        Reported rather than acted on, so the operator can see that a manual
        trade overlaps a scanner signal.
        """
        return any(p.symbol == symbol and p.magic != magic for p in all_positions)

    def trade_permissions(self, account: AccountInfo | None, spec: SymbolSpec | None) -> list[str]:
        """Every reason trading is currently impossible. Empty list means clear."""
        codes: list[str] = []
        if account is None:
            codes.append("NO_ACCOUNT")
        elif not account.trade_allowed:
            codes.append("ACCOUNT_TRADE_DISABLED")

        if spec is None:
            codes.append("NO_SYMBOL_SPEC")
        elif spec.trade_mode in (SYMBOL_TRADE_MODE_DISABLED, SYMBOL_TRADE_MODE_CLOSEONLY):
            codes.append("SYMBOL_TRADE_DISABLED")
        return codes

    def stops_valid(self, plan: TradePlan, spec: SymbolSpec | None) -> list[str]:
        """Stops must clear BOTH the stops level and the freeze level.

        v1.1.0 read the freeze level into its spec struct and then never checked
        it. Inside the freeze band the server refuses modification and closure,
        which is a materially different failure from a too-tight stop: the
        position exists and cannot be managed.
        """
        codes: list[str] = []
        if spec is None or spec.point <= 0.0:
            return ["NO_POINT"]

        required = max(spec.stops_level, spec.freeze_level) * spec.point
        if required <= 0.0:
            return codes  # broker imposes no minimum distance

        if plan.stop_loss > 0.0 and abs(plan.entry - plan.stop_loss) < required:
            codes.append(f"SL_INSIDE_BROKER_LEVEL({required / spec.point:.0f} pts)")
        if plan.take_profit > 0.0 and abs(plan.take_profit - plan.entry) < required:
            codes.append(f"TP_INSIDE_BROKER_LEVEL({required / spec.point:.0f} pts)")
        return codes


class AccountRiskGuard:
    """Daily loss, total drawdown and consecutive losses. Off by default.

    Two corrections that matter more than the thresholds themselves:

    1. **State is persisted.** v1.1.0 set peak equity to *current* equity on
       start, so restarting mid-drawdown reset the high-water mark and quietly
       disarmed the drawdown guard — precisely when it was most needed.
    2. **Only this app's trades count.** v1.1.0 tallied every closing deal on
       the account, so a manual trade or another EA's loss incremented the
       scanner's consecutive-loss counter and could halt it for something it
       never did.
    """

    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()
        self._state = RiskState()
        self._loaded = False

    @property
    def state(self) -> RiskState:
        return self._state

    @staticmethod
    def day_key(now: int) -> int:
        """Broker server day, as ``year * 1000 + day_of_year``."""
        parts = time.gmtime(now)
        return parts.tm_year * 1000 + parts.tm_yday

    def initialize(self, equity: float, now: int, stored: RiskState | None) -> None:
        """Restore persisted state, or seed it on a first ever run."""
        if stored is not None and stored.peak_equity > 0.0:
            self._state = stored
            self._loaded = True
            # Never lower the high-water mark on load; only growth moves it.
            if equity > self._state.peak_equity:
                self._state.peak_equity = equity
        else:
            self._state = RiskState(
                day_key=self.day_key(now),
                day_start_equity=equity,
                peak_equity=equity,
                consecutive_losses=0,
                daily_risk_used_pct=0.0,
            )
            self._loaded = False
        self.roll_day(equity, now)
        self._state.updated_at = now

    @property
    def restored_from_storage(self) -> bool:
        return self._loaded

    def roll_day(self, equity: float, now: int) -> bool:
        """Roll the daily baseline on a server-day change. True if it rolled."""
        key = self.day_key(now)
        if key == self._state.day_key:
            return False
        self._state.day_key = key
        self._state.day_start_equity = equity
        self._state.daily_risk_used_pct = 0.0
        # Consecutive losses deliberately survive the day boundary: a losing
        # streak does not become irrelevant because midnight passed.
        self._state.updated_at = now
        return True

    def register_closed_profit(self, net_profit: float, now: int) -> None:
        """Called only for deals this app opened (magic-filtered upstream)."""
        if net_profit < 0.0:
            self._state.consecutive_losses += 1
        elif net_profit > 0.0:
            self._state.consecutive_losses = 0
        self._state.updated_at = now

    def register_risk_used(self, risk_pct: float, now: int) -> None:
        self._state.daily_risk_used_pct += risk_pct
        self._state.updated_at = now

    def check(self, equity: float, now: int) -> tuple[bool, list[str]]:
        """Returns ``(may_trade, breached_codes)``.

        Every breached guard is reported, not just the first, so the dashboard
        can show the whole picture.
        """
        if not self._config.guards_enabled:
            return True, []

        self.roll_day(equity, now)
        if equity > self._state.peak_equity:
            self._state.peak_equity = equity
            self._state.updated_at = now

        codes: list[str] = []

        if self._state.day_start_equity > 0.0:
            daily_loss_pct = (
                (self._state.day_start_equity - equity) / self._state.day_start_equity * 100.0
            )
            if daily_loss_pct >= self._config.daily_loss_limit_pct:
                codes.append(f"DAILY_LOSS_HALT({daily_loss_pct:.2f}%)")

        if self._state.peak_equity > 0.0:
            drawdown_pct = (self._state.peak_equity - equity) / self._state.peak_equity * 100.0
            if drawdown_pct >= self._config.total_drawdown_limit_pct:
                codes.append(f"DRAWDOWN_HALT({drawdown_pct:.2f}%)")

        if self._state.consecutive_losses >= self._config.max_consecutive_losses:
            codes.append(f"CONSECUTIVE_LOSS_HALT({self._state.consecutive_losses})")

        return len(codes) == 0, codes
