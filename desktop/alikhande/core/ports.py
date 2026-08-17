"""The boundary between the pure core and the outside world.

Everything the scanner needs from a broker is expressed here as a Protocol.
``core`` imports nothing else — no ``MetaTrader5``, no ``PySide6``, no sqlite —
so the entire analysis and risk pipeline can be exercised by tests with a stub
gateway, which is precisely what the MQL5 build could never do.

Two protocols rather than one, and the split is not cosmetic:

``MarketGateway``
    Read-only market information. Bars, ticks, contract specifications. Safe by
    construction — nothing here can move money.

``BrokerGateway``
    Account state, open positions and orders, trade history, and the one method
    that sends an order. A component that only needs quotes is given only a
    ``MarketGateway``, so it is structurally incapable of trading.

``send_order`` is the single method in this file that can affect an account.
Only ``core.execution.ExecutionEngine`` is permitted to call it, and the test
suite asserts that no other module in the package references it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .enums import Timeframe
from .models import (
    AccountInfo,
    Bar,
    DealInfo,
    OrderInfo,
    OrderRequest,
    OrderResult,
    PositionInfo,
    SymbolSpec,
    Tick,
)


class GatewayError(RuntimeError):
    """A gateway could not answer.

    Raised rather than returning a sentinel because every caller of a gateway
    method in this codebase treats "no answer" as a refusal to act. Making that
    an exception means a caller cannot forget to check.
    """


@runtime_checkable
class MarketGateway(Protocol):
    """Read-only market data."""

    def is_connected(self) -> bool:
        """True when the gateway can currently answer questions."""

    def server_time(self) -> int:
        """Broker server time as a Unix timestamp.

        Used for every ``now`` in the system. Local clock time is deliberately
        not used: a signal's TTL, an armed intent's expiry and a news window all
        have to agree with the server's idea of when things happened.
        """

    def symbols(self) -> list[str]:
        """Every symbol the gateway can serve."""

    def resolve_symbol(self, requested: str) -> str | None:
        """Map a requested name onto the broker's actual symbol name.

        Brokers decorate: ``EURUSD`` may really be ``EURUSD_o``, ``EURUSD.m`` or
        ``#EURUSD``. Returns ``None`` when nothing plausibly matches, which is a
        refusal — guessing here would size a trade against the wrong contract.
        """

    def symbol_spec(self, symbol: str) -> SymbolSpec | None:
        """Contract specification, or ``None`` if unavailable."""

    def tick(self, symbol: str) -> Tick | None:
        """Most recent tick, or ``None``."""

    def bars(self, symbol: str, timeframe: Timeframe, count: int) -> list[Bar]:
        """The last ``count`` bars, **chronological, oldest first**.

        Returns fewer than requested — possibly none — when the history is not
        available. Callers must check the length; the analysis engines all
        refuse rather than extrapolate.
        """


@runtime_checkable
class BrokerGateway(MarketGateway, Protocol):
    """Account state, trade history, and the single order-sending method."""

    def account(self) -> AccountInfo | None:
        """Account state, including the demo flag everything keys off."""

    def positions(self, magic: int | None = None) -> list[PositionInfo]:
        """Currently open positions, optionally filtered by magic number."""

    def orders(self, magic: int | None = None) -> list[OrderInfo]:
        """Currently working (unfilled) orders."""

    def history_orders(self, since: int, until: int, magic: int | None = None) -> list[OrderInfo]:
        """Completed orders in the window."""

    def history_deals(self, since: int, until: int, magic: int | None = None) -> list[DealInfo]:
        """Executed deals in the window."""

    def calc_profit(
        self, symbol: str, direction: int, volume: float, price_open: float, price_close: float
    ) -> float | None:
        """Profit/loss for a hypothetical move, in **account currency**.

        This is the broker's own conversion chain and it is the only correct way
        to price a stop on a cross-currency symbol held in a third currency.
        Returning ``None`` means the broker could not answer, and every caller
        treats that as a refusal to size the trade rather than an invitation to
        approximate.
        """

    def calc_margin(
        self, symbol: str, direction: int, volume: float, price: float
    ) -> float | None:
        """Margin required for a hypothetical position, in account currency."""

    def check_order(self, request: OrderRequest) -> tuple[bool, int, str]:
        """Ask the server whether it would accept this order.

        Returns ``(accepted, retcode, comment)``.

        A successful check does NOT guarantee a fill — MetaQuotes is explicit
        about this. It screens out requests certain to be rejected and says
        nothing about what the market does next, which is why the result still
        has to be reconciled after submission.
        """

    def send_order(self, request: OrderRequest) -> OrderResult:
        """Send an order.

        **The only method in this codebase that can move money.** Implementations
        must refuse on a non-demo account independently of any caller-side check
        — see ``adapters/mt5/gateway.py``. Defence in depth is deliberate here:
        the caller-side block and the gateway-side block share no code, so one
        being edited away does not silently disable the other.
        """
