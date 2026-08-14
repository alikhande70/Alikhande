"""A fake MetaTrader 5 terminal, good enough to run the real adapter against.

``adapters/mt5/gateway.py`` is the module that decides whether this application
works at all on a real account, and until now **nothing had ever executed a
single line of it**. That is how a defect that broke every live pass — the
gateway attaching on the UI thread and then refusing every call from the scan
worker — survived a green test suite, a static gate and two rounds of review.

The fix is not more careful reading. It is a double: an object exposing the
subset of the ``MetaTrader5`` module surface this adapter actually touches,
installed into ``sys.modules`` so ``import MetaTrader5`` finds it. The adapter
does not know the difference, so the code under test is the real code.

## What this proves and what it does not

It proves the adapter's **own logic**: thread ownership, symbol resolution,
specification mapping, request construction, filling-mode selection, retcode
interpretation, and that ``send_order`` refuses a real account independently of
every caller.

It does not prove that MetaQuotes' package behaves as modelled here. The
constants, the field names and the semantics come from published documentation,
and a double built from documentation inherits every misunderstanding in it.
That gap closes on a Windows machine with a real terminal and nowhere else,
which is exactly what ``docs/VERIFICATION.md`` says.

Deliberately faithful about the awkward parts, because those are where the
adapter's bugs live: ``initialize()`` returns ``True`` when already
initialised without re-attaching, ``copy_rates_from_pos`` returns ``None``
rather than an empty list on failure, and ``order_check`` reports ``0`` for
"would be accepted" while ``order_send`` reports ``10009`` for "done".
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass

# ---- the constants the adapter reads -------------------------------------
TRADE_ACTION_DEAL = 1
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
ORDER_TIME_GTC = 0
ORDER_FILLING_FOK = 0
ORDER_FILLING_IOC = 1
ORDER_FILLING_RETURN = 2

SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2

TIMEFRAME_M1 = 1
TIMEFRAME_M5 = 5
TIMEFRAME_M15 = 15
TIMEFRAME_M30 = 30
TIMEFRAME_H1 = 16385
TIMEFRAME_H4 = 16388
TIMEFRAME_D1 = 16408


class Rate:
    """One bar, indexed by field name.

    ``copy_rates_from_pos`` returns a numpy structured array, whose records are
    read as ``row["time"]`` rather than ``row[0]``. A double returning plain
    tuples would let a positional-indexing bug pass here and fail on a real
    terminal, so this mirrors the access pattern rather than the storage.
    """

    __slots__ = ("_fields",)

    def __init__(self, **fields):
        self._fields = fields

    def __getitem__(self, key):
        return self._fields[key]

    def keys(self):
        return self._fields.keys()


@dataclass
class FakeSymbol:
    name: str = "EURUSD"
    digits: int = 5
    point: float = 0.00001
    trade_tick_size: float = 0.00001
    trade_tick_value: float = 1.0
    trade_contract_size: float = 100_000.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    trade_stops_level: int = 10
    trade_freeze_level: int = 0
    trade_mode: int = 4
    currency_base: str = "EUR"
    currency_profit: str = "USD"
    currency_margin: str = "EUR"
    visible: bool = True
    #: Bitmask. 0 means the symbol supports neither FOK nor IOC, which is a real
    #: broker configuration and the one that used to produce a guaranteed 10030.
    filling_mode: int = SYMBOL_FILLING_FOK | SYMBOL_FILLING_IOC


@dataclass
class FakeAccount:
    login: int = 5_000_123
    server: str = "Broker-Demo"
    currency: str = "USD"
    company: str = "Broker Ltd"
    name: str = "Test Account"
    balance: float = 10_000.0
    equity: float = 10_000.0
    margin: float = 0.0
    margin_free: float = 10_000.0
    leverage: int = 100
    #: 0 demo, 1 real, 2 contest.
    trade_mode: int = 0
    trade_allowed: bool = True


@dataclass
class FakeTerminal:
    build: int = 4260
    trade_allowed: bool = True
    connected: bool = True


class FakeMT5:
    """The module double. Install with :func:`install`."""

    __version__ = "5.0.45"

    # Re-exported so `mt5.TRADE_ACTION_DEAL` works on the instance.
    TRADE_ACTION_DEAL = TRADE_ACTION_DEAL
    ORDER_TYPE_BUY = ORDER_TYPE_BUY
    ORDER_TYPE_SELL = ORDER_TYPE_SELL
    ORDER_TIME_GTC = ORDER_TIME_GTC
    ORDER_FILLING_FOK = ORDER_FILLING_FOK
    ORDER_FILLING_IOC = ORDER_FILLING_IOC
    ORDER_FILLING_RETURN = ORDER_FILLING_RETURN
    TIMEFRAME_M1 = TIMEFRAME_M1
    TIMEFRAME_M5 = TIMEFRAME_M5
    TIMEFRAME_M15 = TIMEFRAME_M15
    TIMEFRAME_M30 = TIMEFRAME_M30
    TIMEFRAME_H1 = TIMEFRAME_H1
    TIMEFRAME_H4 = TIMEFRAME_H4
    TIMEFRAME_D1 = TIMEFRAME_D1

    def __init__(self) -> None:
        self.initialised = False
        self.initialise_calls = 0
        self.shutdown_calls = 0
        self.initialise_should_fail = False
        self.error: tuple[int, str] = (0, "ok")

        self.terminal = FakeTerminal()
        self.account: FakeAccount | None = FakeAccount()
        self.symbols_map: dict[str, FakeSymbol] = {
            "EURUSD": FakeSymbol(),
            "XAUUSD": FakeSymbol(
                name="XAUUSD",
                digits=2,
                point=0.01,
                trade_tick_size=0.01,
                trade_contract_size=100.0,
                currency_base="XAU",
                currency_margin="XAU",
            ),
            # A broker that decorates its names, which symbol resolution has to
            # cope with and which no offline test exercises.
            "GBPUSD.m": FakeSymbol(name="GBPUSD.m", currency_base="GBP"),
        }
        self.selected: list[str] = []
        self.sent: list[dict] = []
        self.checked: list[dict] = []
        self.send_retcode = 10009
        self.check_retcode = 0
        self.rates: dict[tuple[str, int], list] = {}

    # ---- lifecycle --------------------------------------------------------
    def initialize(self, **kwargs) -> bool:
        self.initialise_calls += 1
        if self.initialise_should_fail:
            self.error = (-10005, "IPC timeout")
            return False
        # Faithful: an already-initialised terminal answers True without
        # re-attaching. A reconnect that does not shut down first therefore
        # changes nothing while reporting success.
        self.initialised = True
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        self.initialised = False

    def last_error(self):
        return self.error

    def terminal_info(self):
        return self.terminal if self.initialised else None

    def account_info(self):
        return self.account if self.initialised else None

    # ---- symbols ----------------------------------------------------------
    def symbols_get(self):
        return list(self.symbols_map.values())

    def symbol_info(self, name: str):
        return self.symbols_map.get(name)

    def symbol_select(self, name: str, enable: bool = True) -> bool:
        if name not in self.symbols_map:
            return False
        self.selected.append(name)
        return True

    def symbol_info_tick(self, name: str):
        symbol = self.symbols_map.get(name)
        if symbol is None:
            return None
        mid = 2000.0 if name.startswith("XAU") else 1.10000
        return types.SimpleNamespace(
            time=1_700_000_000, bid=mid, ask=mid + symbol.point * 10, last=mid, volume=1
        )

    # ---- history ----------------------------------------------------------
    def copy_rates_from_pos(self, symbol: str, timeframe: int, start: int, count: int):
        key = (symbol, timeframe)
        if key not in self.rates:
            # Faithful: failure is None, not an empty sequence. Code that does
            # `len(result)` without checking raises a TypeError here, which is
            # exactly what it would do against the real package.
            return None
        return self.rates[key][-count:]

    def load_rates(self, symbol: str, timeframe: int, count: int = 400) -> None:
        base = 2000.0 if symbol.startswith("XAU") else 1.10000
        step = 0.5 if symbol.startswith("XAU") else 0.0001
        rows = []
        for i in range(count):
            open_ = base + i * step * 0.1
            rows.append(
                Rate(
                    time=1_700_000_000 + i * 300,
                    open=open_,
                    high=open_ + step,
                    low=open_ - step,
                    close=open_ + step * 0.5,
                    tick_volume=100 + i,
                    spread=2,
                    real_volume=0,
                )
            )
        self.rates[(symbol, timeframe)] = rows

    def positions_get(self, **kwargs):
        return []

    def orders_get(self, **kwargs):
        return []

    def history_orders_get(self, *args, **kwargs):
        return []

    def history_deals_get(self, *args, **kwargs):
        return []

    # ---- pricing ----------------------------------------------------------
    def order_calc_profit(self, order_type, symbol, volume, price_open, price_close):
        sign = 1.0 if order_type == ORDER_TYPE_BUY else -1.0
        return sign * (price_close - price_open) * volume * 100_000.0

    def order_calc_margin(self, order_type, symbol, volume, price):
        return volume * price * 1000.0

    # ---- orders -----------------------------------------------------------
    def order_check(self, request: dict):
        self.checked.append(dict(request))
        return types.SimpleNamespace(
            retcode=self.check_retcode, comment="Done", request=request
        )

    def order_send(self, request: dict):
        self.sent.append(dict(request))
        return types.SimpleNamespace(
            retcode=self.send_retcode,
            order=777,
            deal=888,
            request_id=999,
            volume=request.get("volume", 0.0),
            price=request.get("price", 0.0),
            comment="Done",
        )


def install(fake: FakeMT5 | None = None) -> FakeMT5:
    """Put the double where ``import MetaTrader5`` will find it."""
    fake = fake or FakeMT5()
    sys.modules["MetaTrader5"] = fake  # type: ignore[assignment]
    return fake


def uninstall() -> None:
    sys.modules.pop("MetaTrader5", None)
