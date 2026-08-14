"""The MetaTrader 5 gateway.

This is the module that makes the app talk to a real broker, and it is the only
one in the package that imports ``MetaTrader5``.

**What "outside MetaTrader" actually means, stated once, precisely.** MetaQuotes
publishes exactly one supported way for an external program to reach an MT5
account: the ``MetaTrader5`` Python package, which communicates with a *running*
terminal over local IPC. There is no MT5 REST endpoint, no FIX gateway in the
retail product, and no documented wire protocol. So this application is a
genuinely separate Windows program — its own process, window, database and
logic, with MetaTrader nowhere in its UI — but the terminal must be installed,
running and logged in, acting purely as a quote and execution gateway.

Requirements the terminal must satisfy, all of them non-negotiable:

* MetaTrader 5 running and logged in to the account.
* Algo Trading enabled in the terminal (Tools → Options → Expert Advisors).
* The symbols in use visible in Market Watch, or ``symbol_select`` will fail.
* Same bitness/architecture assumptions as the ``MetaTrader5`` wheel — it is
  Windows-only, which is why this module degrades to a clear error elsewhere
  rather than pretending.

**Threading.** The ``MetaTrader5`` package keeps process-global connection
state and is not safe to call from several threads at once. Every method here
must be called from the single scan-worker thread. The UI thread never touches
this class; it reads snapshots the worker produced. This is enforced by
convention and asserted in ``_require_owner_thread``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from ...core.enums import Direction, Timeframe
from ...core.models import (
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
from ...core.ports import GatewayError
from ..offline.gateway import spec_fingerprint


class MT5Unavailable(GatewayError):
    """The MetaTrader5 package is not importable, or the terminal is unreachable."""


def _import_mt5() -> Any:
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - platform dependent
        raise MT5Unavailable(
            "the MetaTrader5 package is not installed or not importable. It is "
            "Windows-only and requires a running MetaTrader 5 terminal. "
            "Install with: pip install MetaTrader5"
        ) from error
    return mt5


@dataclass(frozen=True)
class TerminalProbe:
    """What a short attach-and-detach found out about the machine.

    Used at startup to decide the environment and where evidence should live,
    *before* the scan worker exists to own the real connection. It attaches,
    reads, and detaches again — it deliberately does not leave a connection
    behind, because that connection would belong to the wrong thread.
    """

    available: bool = False
    reason: str = ""
    build: int = 0
    trade_allowed: bool = False
    login: int = 0
    server: str = ""
    is_demo: bool | None = None

    @property
    def account_known(self) -> bool:
        return self.is_demo is not None


def probe_terminal() -> TerminalProbe:
    """Attach briefly, report, detach. Never raises."""
    try:
        mt5 = _import_mt5()
    except MT5Unavailable as error:
        return TerminalProbe(available=False, reason=str(error))

    try:
        if not mt5.initialize():
            code, message = mt5.last_error()
            return TerminalProbe(
                available=False, reason=f"terminal not reachable ({code}: {message})"
            )
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        return TerminalProbe(
            available=True,
            build=int(getattr(terminal, "build", 0) or 0),
            trade_allowed=bool(getattr(terminal, "trade_allowed", False)),
            login=int(getattr(account, "login", 0) or 0) if account else 0,
            server=str(getattr(account, "server", "") or "") if account else "",
            # ``trade_mode`` 0 is demo, 1 real, 2 contest. None when no account
            # answered — which must never collapse into "not demo", because the
            # environment verdict keys off exactly this distinction.
            is_demo=(int(account.trade_mode) == 0) if account is not None else None,
        )
    except Exception as error:  # pragma: no cover - defensive
        return TerminalProbe(available=False, reason=f"{type(error).__name__}: {error}")
    finally:
        try:
            mt5.shutdown()
        except Exception:  # pragma: no cover - defensive
            pass


class MT5Gateway:
    """Implements ``BrokerGateway`` against a live MetaTrader 5 terminal."""

    def __init__(self, **connect_options: Any) -> None:
        self._mt5: Any = None
        self._owner_thread: int | None = None
        self._spec_cache: dict[str, SymbolSpec] = {}
        self._selected: set[str] = set()
        # Held rather than applied. `ensure_connected` uses them on whichever
        # thread calls it, which is how the owner thread ends up being the one
        # that will actually make the calls.
        self._connect_options = connect_options

    # ------------------------------------------------------------- lifecycle
    def connect(
        self,
        *,
        path: str | None = None,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        timeout_ms: int = 60_000,
    ) -> None:
        """Attach to the terminal.

        With no credentials this attaches to whatever account the terminal is
        already logged into, which is the normal case and the one that requires
        the operator to have made the choice deliberately in MetaTrader rather
        than storing a password here.
        """
        mt5 = _import_mt5()

        kwargs: dict[str, Any] = {"timeout": timeout_ms}
        if path:
            kwargs["path"] = path
        if login is not None:
            kwargs["login"] = int(login)
        if password:
            kwargs["password"] = password
        if server:
            kwargs["server"] = server

        if not mt5.initialize(**kwargs):
            code, message = mt5.last_error()
            raise MT5Unavailable(
                f"could not attach to the MetaTrader 5 terminal ({code}: {message}). "
                "Check that it is running, logged in, and that Algo Trading is enabled."
            )

        # Assigned only after `initialize` succeeded. Setting them first left a
        # failed connection looking attached: `_mt5` was non-None, so
        # `is_connected()` went on to call into a terminal that had refused us,
        # and `ensure_connected()` would have reported success and never
        # retried.
        self._mt5 = mt5
        self._owner_thread = threading.get_ident()

    def ensure_connected(self) -> bool:
        """Connect if not already, **on the calling thread**.

        This exists because of a defect that made the entire live path
        unusable and which no test could have caught, since nothing ever ran
        this class.

        ``build_application`` runs on the UI thread. It used to call
        ``connect()`` there, which stamped the UI thread as the owner. The scan
        worker then ran on a ``QThread`` and every single gateway call it made
        hit ``_require_owner_thread`` and raised. The engine's ``_safe_*``
        wrappers swallow exceptions, so the window reported "disconnected"
        while the terminal was in fact attached — a silent, permanent, entirely
        misleading failure.

        The guard was not the bug; the guard was right. Connecting on the wrong
        thread was. So connection is now deferred to whoever is going to use
        the gateway, and the worker calls this before its first pass.

        Idempotent, and safe to call every pass. Returns whether a usable
        connection exists.
        """
        if self._mt5 is not None and self._owner_thread == threading.get_ident():
            return True
        if self._mt5 is not None:
            # Attached, but to a different thread. Reconnecting here would let
            # the owner silently migrate, which defeats the guard entirely.
            # Refuse loudly instead: this can only happen if the application
            # wired its threads wrongly, and that is a defect to fix, not to
            # paper over at runtime.
            raise GatewayError(
                "MT5Gateway is already connected on a different thread. "
                "ensure_connected() must be called from the thread that will "
                "make the calls — the scan worker."
            )
        self.connect(**self._connect_options)
        return self._mt5 is not None

    def reconnect(self) -> bool:
        """Drop the attachment and take a fresh one on the calling thread.

        What the robot's auto-reconnect actually does. Shutting down first
        matters: ``mt5.initialize()`` against an already-initialised terminal
        returns success without re-establishing anything, so a reconnect that
        skipped the shutdown would report success and change nothing — which is
        the worst possible outcome for a recovery path.
        """
        self.shutdown()
        try:
            return self.ensure_connected()
        except GatewayError:
            return False

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
            self._mt5 = None
            self._owner_thread = None

    def _require_owner_thread(self) -> Any:
        if self._mt5 is None:
            raise MT5Unavailable("gateway is not connected")
        if self._owner_thread is not None and threading.get_ident() != self._owner_thread:
            # Loud rather than best-effort. The MetaTrader5 package holds
            # process-global connection state; a cross-thread call corrupts it
            # in ways that surface much later as inexplicable empty results.
            raise GatewayError(
                "MT5Gateway was called from a thread other than the one that "
                "connected it. All terminal access must stay on the scan worker."
            )
        return self._mt5

    # ---------------------------------------------------------- market data
    def is_connected(self) -> bool:
        if self._mt5 is None:
            return False
        try:
            return self._mt5.terminal_info() is not None
        except Exception:
            return False

    def server_time(self) -> int:
        """Broker server time, taken from a live tick.

        Deliberately *not* the local clock. ``mt5`` exposes no direct server
        clock, and a tick's timestamp is the server's own opinion of now, which
        is what every TTL and news window in the system must agree with.
        """
        mt5 = self._require_owner_thread()
        for symbol in list(self._selected) or [s.name for s in (mt5.symbols_get() or [])[:1]]:
            tick = mt5.symbol_info_tick(symbol)
            if tick is not None and tick.time:
                return int(tick.time)
        raise GatewayError("no tick available to establish server time")

    def symbols(self) -> list[str]:
        mt5 = self._require_owner_thread()
        return [s.name for s in (mt5.symbols_get() or [])]

    def resolve_symbol(self, requested: str) -> str | None:
        """Map a requested name onto the broker's actual symbol name.

        Brokers decorate: ``EURUSD`` may really be ``EURUSD_o``, ``EURUSD.m`` or
        ``#EURUSD``. Exact match wins, then case-insensitive, then a decorated
        variant whose alphabetic core matches. Ambiguity is a refusal: two
        equally plausible candidates mean the operator must say which, because
        sizing a trade against the wrong contract is not a recoverable mistake.
        """
        mt5 = self._require_owner_thread()
        available = self.symbols()
        if requested in available:
            self._select(requested)
            return requested

        wanted = requested.upper()
        exact = [s for s in available if s.upper() == wanted]
        if len(exact) == 1:
            self._select(exact[0])
            return exact[0]

        def core(name: str) -> str:
            return "".join(ch for ch in name.upper() if ch.isalpha())

        candidates = [s for s in available if core(s).startswith(wanted)]
        if len(candidates) == 1:
            self._select(candidates[0])
            return candidates[0]
        return None

    def _select(self, symbol: str) -> None:
        """Ensure the symbol is in Market Watch, or history calls return nothing."""
        if symbol in self._selected:
            return
        mt5 = self._require_owner_thread()
        if mt5.symbol_select(symbol, True):
            self._selected.add(symbol)

    def symbol_spec(self, symbol: str) -> SymbolSpec | None:
        mt5 = self._require_owner_thread()
        self._select(symbol)
        info = mt5.symbol_info(symbol)
        if info is None:
            return None

        spec = SymbolSpec(
            symbol=info.name,
            digits=int(info.digits),
            point=float(info.point),
            tick_size=float(info.trade_tick_size),
            tick_value=float(info.trade_tick_value),
            contract_size=float(info.trade_contract_size),
            volume_min=float(info.volume_min),
            volume_max=float(info.volume_max),
            volume_step=float(info.volume_step),
            stops_level=int(info.trade_stops_level),
            freeze_level=int(info.trade_freeze_level),
            trade_mode=int(info.trade_mode),
            currency_base=info.currency_base,
            currency_profit=info.currency_profit,
            currency_margin=info.currency_margin,
            ready=True,
        )
        spec.fingerprint = spec_fingerprint(spec)
        self._spec_cache[symbol] = spec
        return spec

    def _timeframe(self, timeframe: Timeframe) -> int:
        mt5 = self._require_owner_thread()
        mapping = {
            Timeframe.M1: mt5.TIMEFRAME_M1,
            Timeframe.M5: mt5.TIMEFRAME_M5,
            Timeframe.M15: mt5.TIMEFRAME_M15,
            Timeframe.M30: mt5.TIMEFRAME_M30,
            Timeframe.H1: mt5.TIMEFRAME_H1,
            Timeframe.H4: mt5.TIMEFRAME_H4,
            Timeframe.D1: mt5.TIMEFRAME_D1,
        }
        return mapping[timeframe]

    def tick(self, symbol: str) -> Tick | None:
        mt5 = self._require_owner_thread()
        self._select(symbol)
        raw = mt5.symbol_info_tick(symbol)
        if raw is None or raw.time == 0:
            return None
        return Tick(
            time=int(raw.time),
            bid=float(raw.bid),
            ask=float(raw.ask),
            last=float(raw.last),
            volume=int(raw.volume),
        )

    def bars(self, symbol: str, timeframe: Timeframe, count: int) -> list[Bar]:
        """The last ``count`` bars, chronological, oldest first.

        ``copy_rates_from_pos(symbol, tf, 0, count)`` already returns
        chronological order with the still-forming bar last, which matches the
        convention the analysis engines expect — they drop that last bar
        themselves.
        """
        mt5 = self._require_owner_thread()
        self._select(symbol)
        rates = mt5.copy_rates_from_pos(symbol, self._timeframe(timeframe), 0, count)
        if rates is None or len(rates) == 0:
            return []
        return [
            Bar(
                time=int(r["time"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                tick_volume=int(r["tick_volume"]),
                spread=int(r["spread"]),
                real_volume=int(r["real_volume"]),
            )
            for r in rates
        ]

    # -------------------------------------------------------- account state
    def account(self) -> AccountInfo | None:
        mt5 = self._require_owner_thread()
        info = mt5.account_info()
        if info is None:
            return None
        # ACCOUNT_TRADE_MODE_DEMO == 0. Anything else — real (1) or contest (2)
        # — is not a demo account and must never be traded by this build.
        return AccountInfo(
            login=int(info.login),
            server=info.server,
            currency=info.currency,
            company=info.company,
            name=info.name,
            balance=float(info.balance),
            equity=float(info.equity),
            margin=float(info.margin),
            margin_free=float(info.margin_free),
            leverage=int(info.leverage),
            is_demo=int(info.trade_mode) == 0,
            trade_allowed=bool(info.trade_allowed),
        )

    def positions(self, magic: int | None = None) -> list[PositionInfo]:
        mt5 = self._require_owner_thread()
        raw = mt5.positions_get()
        if raw is None:
            return []
        out = []
        for p in raw:
            if magic is not None and int(p.magic) != magic:
                continue
            out.append(
                PositionInfo(
                    ticket=int(p.ticket),
                    symbol=p.symbol,
                    magic=int(p.magic),
                    position_id=int(p.identifier),
                    direction=Direction.LONG if int(p.type) == 0 else Direction.SHORT,
                    volume=float(p.volume),
                    price_open=float(p.price_open),
                    stop_loss=float(p.sl),
                    take_profit=float(p.tp),
                    profit=float(p.profit),
                    time=int(p.time),
                )
            )
        return out

    def orders(self, magic: int | None = None) -> list[OrderInfo]:
        mt5 = self._require_owner_thread()
        raw = mt5.orders_get()
        if raw is None:
            return []
        return [
            OrderInfo(
                ticket=int(o.ticket),
                symbol=o.symbol,
                magic=int(o.magic),
                state=_order_state_name(int(o.state)),
                volume_initial=float(o.volume_initial),
                volume_current=float(o.volume_current),
                price_open=float(o.price_open),
                time_setup=int(o.time_setup),
            )
            for o in raw
            if magic is None or int(o.magic) == magic
        ]

    def history_orders(self, since: int, until: int, magic: int | None = None) -> list[OrderInfo]:
        mt5 = self._require_owner_thread()
        raw = mt5.history_orders_get(_dt(since), _dt(until))
        if raw is None:
            return []
        return [
            OrderInfo(
                ticket=int(o.ticket),
                symbol=o.symbol,
                magic=int(o.magic),
                state=_order_state_name(int(o.state)),
                volume_initial=float(o.volume_initial),
                volume_current=float(o.volume_current),
                price_open=float(o.price_open),
                time_setup=int(o.time_setup),
            )
            for o in raw
            if magic is None or int(o.magic) == magic
        ]

    def history_deals(self, since: int, until: int, magic: int | None = None) -> list[DealInfo]:
        mt5 = self._require_owner_thread()
        raw = mt5.history_deals_get(_dt(since), _dt(until))
        if raw is None:
            return []
        return [
            DealInfo(
                ticket=int(d.ticket),
                order=int(d.order),
                position_id=int(d.position_id),
                symbol=d.symbol,
                magic=int(d.magic),
                entry=int(d.entry),
                volume=float(d.volume),
                price=float(d.price),
                profit=float(d.profit),
                commission=float(d.commission),
                swap=float(d.swap),
                time=int(d.time),
            )
            for d in raw
            if magic is None or int(d.magic) == magic
        ]

    # -------------------------------------------------------------- pricing
    def calc_profit(
        self, symbol: str, direction: int, volume: float, price_open: float, price_close: float
    ) -> float | None:
        """Delegated to the broker. There is no fallback formula on purpose.

        This is the broker's own currency-conversion chain, and it is the only
        correct answer for a cross-currency symbol on an account denominated in
        a third currency. If it cannot answer, the trade is not sized — an
        approximation here would be a number that looks like risk control and
        is not.
        """
        mt5 = self._require_owner_thread()
        order_type = mt5.ORDER_TYPE_BUY if direction == int(Direction.LONG) else mt5.ORDER_TYPE_SELL
        result = mt5.order_calc_profit(order_type, symbol, volume, price_open, price_close)
        return None if result is None else float(result)

    def calc_margin(self, symbol: str, direction: int, volume: float, price: float) -> float | None:
        mt5 = self._require_owner_thread()
        order_type = mt5.ORDER_TYPE_BUY if direction == int(Direction.LONG) else mt5.ORDER_TYPE_SELL
        result = mt5.order_calc_margin(order_type, symbol, volume, price)
        return None if result is None else float(result)

    # -------------------------------------------------------------- ordering
    def _build_request(self, request: OrderRequest) -> dict[str, Any]:
        mt5 = self._require_owner_thread()
        info = mt5.symbol_info(request.symbol)
        if info is None:
            raise GatewayError(f"no symbol info for {request.symbol}")

        # Filling policy comes from the symbol rather than a hardcoded guess; an
        # unsupported filling mode is the most common source of retcode 10030.
        #
        # The bitmask reports which of FOK (1) and IOC (2) the symbol supports.
        # A symbol may report **neither**, which is an ordinary configuration on
        # Market Execution accounts, and the previous code defaulted to IOC in
        # exactly that case — asking for the one policy the symbol had just said
        # it does not accept, and guaranteeing a rejection. RETURN is the
        # documented remaining option and is what those symbols want.
        mode = int(getattr(info, "filling_mode", 0) or 0)
        if mode & 1:  # SYMBOL_FILLING_FOK
            filling = mt5.ORDER_FILLING_FOK
        elif mode & 2:  # SYMBOL_FILLING_IOC
            filling = mt5.ORDER_FILLING_IOC
        else:
            filling = mt5.ORDER_FILLING_RETURN

        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": request.symbol,
            "volume": float(request.volume),
            "type": (
                mt5.ORDER_TYPE_BUY
                if request.direction == Direction.LONG
                else mt5.ORDER_TYPE_SELL
            ),
            "price": float(request.price),
            "sl": float(request.stop_loss),
            "tp": float(request.take_profit),
            "deviation": int(request.deviation),
            "magic": int(request.magic),
            # MetaTrader stores an order comment in a fixed 32-byte field and
            # truncates anything longer itself. Truncating here means the
            # comment this application *recorded* matches the one the broker
            # actually holds — otherwise reconciliation compares a string
            # against its own truncated copy and reports a mismatch that is
            # purely an artefact of the field width.
            "comment": str(request.comment)[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

    def check_order(self, request: OrderRequest) -> tuple[bool, int, str]:
        mt5 = self._require_owner_thread()
        result = mt5.order_check(self._build_request(request))
        if result is None:
            code, message = mt5.last_error()
            return False, int(code), str(message)
        # order_check reports 0 for "would be accepted"; MetaQuotes is explicit
        # that this does not promise a fill.
        accepted = int(result.retcode) == 0
        return accepted, int(result.retcode), str(result.comment)

    def send_order(self, request: OrderRequest) -> OrderResult:
        """Send an order. Refuses any non-demo account, independently.

        The execution engine already refused a real account before reaching
        here. This second refusal shares no code with that one and is not
        reachable around it: even a caller that bypassed the engine entirely
        cannot get an order out on a live account through this gateway.
        """
        mt5 = self._require_owner_thread()

        account = self.account()
        if account is None:
            return OrderResult(ok=False, retcode=0, comment="NO_ACCOUNT")
        if not account.is_demo:
            return OrderResult(ok=False, retcode=0, comment="REAL_ACCOUNT_BLOCKED")

        result = mt5.order_send(self._build_request(request))
        if result is None:
            code, message = mt5.last_error()
            return OrderResult(ok=False, retcode=int(code), comment=str(message))

        retcode = int(result.retcode)
        return OrderResult(
            # 10009 DONE, 10008 PLACED, 10010 DONE_PARTIAL are the accepted set.
            ok=retcode in (10008, 10009, 10010),
            retcode=retcode,
            order=int(result.order),
            deal=int(result.deal),
            request_id=int(getattr(result, "request_id", 0) or 0),
            volume=float(result.volume),
            price=float(result.price),
            comment=str(result.comment),
        )


def _dt(timestamp: int):
    """MetaTrader's history functions take datetimes, not epoch integers."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _order_state_name(state: int) -> str:
    """MetaTrader ORDER_STATE_* as a name the core can compare.

    The core maps names rather than integers so an adapter for a different
    broker could supply its own vocabulary without the reconciliation logic
    learning MetaTrader's numbering.
    """
    return {
        0: "STARTED",
        1: "PLACED",
        2: "CANCELED",
        3: "PARTIAL",
        4: "FILLED",
        5: "REJECTED",
        6: "EXPIRED",
        7: "REQUEST_ADD",
        8: "REQUEST_MODIFY",
        9: "REQUEST_CANCEL",
    }.get(state, "UNKNOWN")
