"""A deterministic gateway backed by in-memory bars.

Two jobs, and it is worth being clear that they are different:

**Backtesting.** Load real bars exported from MetaTrader and replay them. The
gateway advances a cursor; ``bars()`` returns only history up to the cursor, so
the analysis engines cannot see the future no matter what they ask for. This is
the mechanism that makes look-ahead structurally impossible rather than merely
discouraged.

**Running the app with nothing attached.** Synthetic bars from a seeded
generator, so the UI, the persistence layer and the whole pipeline can be
exercised — and tested in CI — on a machine with no MetaTrader anywhere.

The synthetic generator exists to prove the *machinery* works. Numbers produced
from it are not evidence about markets and the backtest report says so on every
run. Confusing the two would be exactly the sin this codebase is built to avoid.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ...core.enums import Direction, Timeframe
from ...core.hashing import fnv1a64
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

RETCODE_DONE = 10009


def spec_fingerprint(spec: SymbolSpec) -> str:
    """Hash of the fields position sizing depends on.

    Only the risk-relevant fields. A broker renaming a symbol's description does
    not invalidate stored position sizes; a broker changing its tick value does.
    """
    return fnv1a64(
        f"{spec.symbol}|{spec.digits}|{spec.point:.10f}|{spec.tick_size:.10f}|"
        f"{spec.tick_value:.10f}|{spec.contract_size:.4f}|{spec.volume_min:.4f}|"
        f"{spec.volume_step:.4f}|{spec.stops_level}|{spec.freeze_level}"
    )


def default_spec(symbol: str) -> SymbolSpec:
    """A plausible FX/metal specification.

    Every number here is ``[ASSUMED]`` in the strict sense of the word — they
    describe no real broker. They exist so the pipeline has something
    self-consistent to size against offline, and the backtest report labels any
    result computed with them accordingly.
    """
    metal = symbol.upper().startswith(("XAU", "XAG"))
    jpy = symbol.upper().endswith("JPY")

    # tick_value is the account-currency value of one tick_size move on ONE lot.
    # Getting it wrong does not error — it silently mis-sizes every position, so
    # each line states its arithmetic.
    if metal:
        # 100 oz contract x 0.01 tick = $1.00 per tick per lot.
        digits, point, tick_value, contract = 2, 0.01, 1.00, 100.0
    elif jpy:
        # 100k contract x 0.001 tick ~ $0.90 per tick per lot near USDJPY 110.
        digits, point, tick_value, contract = 3, 0.001, 0.90, 100_000.0
    else:
        # 100k contract x 0.00001 tick = $1.00 per tick per lot on a USD quote.
        digits, point, tick_value, contract = 5, 0.00001, 1.00, 100_000.0

    spec = SymbolSpec(
        symbol=symbol,
        digits=digits,
        point=point,
        tick_size=point,
        tick_value=tick_value,
        contract_size=contract,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        stops_level=0,
        freeze_level=0,
        trade_mode=4,  # SYMBOL_TRADE_MODE_FULL
        ready=True,
    )
    base, quote = symbol[:3].upper(), symbol[3:6].upper()
    spec.currency_base = base
    spec.currency_profit = quote
    spec.currency_margin = base
    spec.fingerprint = spec_fingerprint(spec)
    return spec


def synthesise_bars(
    symbol: str,
    timeframe: Timeframe,
    count: int,
    *,
    seed: int = 20260806,
    start_price: float | None = None,
    start_time: int = 1_700_000_000,
) -> list[Bar]:
    """Seeded pseudo-market bars: slow trend cycles, faster swings, noise.

    Deterministic for a given ``(symbol, timeframe, seed)`` so a test asserting
    on a backtest result stays valid.

    **Calibration matters here and is easy to get wrong.** An earlier version
    used a per-bar volatility around 6 pips on M5, which compounds into an H1
    ATR near 100 pips on EURUSD — roughly ten times reality. Nothing errors on
    data like that; the scanner simply never finds price near a zone, and the
    backtest reports "no setups" for a reason that has nothing to do with the
    strategy. So the scale below targets a realistic H1 ATR (~10–15 pips on a
    major, ~$3–5 on gold), reached by making the M5 bar range about
    ``h1_atr / sqrt(12)``.

    The two cycles are deliberately long: a trend has to persist for tens of H1
    bars before H4 and H1 can agree about it, and multi-timeframe alignment is
    what the setups are built on. Short cycles produce a market that is always
    in conflict with itself.

    This is a *generator*, not a market model. It produces the regime variety
    the pipeline needs to exercise — trends, pullbacks, ranges — and nothing
    computed from it is evidence about any real instrument.
    """
    rng = random.Random(f"{symbol}|{timeframe.label}|{seed}")
    upper = symbol.upper()

    if upper.startswith("XAU"):
        price = start_price if start_price is not None else 1950.0
        target_h1_atr = 3.50
    elif upper.endswith("JPY"):
        price = start_price if start_price is not None else 148.00
        target_h1_atr = 0.150
    else:
        price = start_price if start_price is not None else 1.1000
        target_h1_atr = 0.00120

    # Scale the per-bar move so that aggregating to H1 lands near the target
    # ATR. A random walk's range grows with the square root of the number of
    # steps, hence the sqrt.
    steps_per_h1 = max(1.0, 3600.0 / timeframe.seconds)
    scale = target_h1_atr / math.sqrt(steps_per_h1) / 2.5

    # Cycle periods in *hours*, converted to bars, so every timeframe describes
    # the same underlying market rhythm.
    slow_period = 120.0 * steps_per_h1  # ~5 days
    fast_period = 18.0 * steps_per_h1  # ~18 hours

    bars: list[Bar] = []
    for i in range(count):
        cycle = (
            math.sin(2.0 * math.pi * i / slow_period) * 0.45
            + math.sin(2.0 * math.pi * i / fast_period) * 0.22
        )
        drift = cycle * scale + rng.gauss(0.0, scale)
        close = max(price * 0.5, price + drift)

        body_high = max(price, close)
        body_low = min(price, close)
        high = body_high + abs(rng.gauss(0.0, scale * 0.55))
        low = max(1e-6, body_low - abs(rng.gauss(0.0, scale * 0.55)))

        bars.append(
            Bar(
                time=start_time + i * timeframe.seconds,
                open=price,
                high=high,
                low=low,
                close=close,
                tick_volume=rng.randint(40, 400),
            )
        )
        price = close
    return bars


@dataclass
class OfflineGateway:
    """In-memory market and broker, with a cursor that hides the future."""

    equity: float = 10_000.0
    balance: float = 10_000.0
    currency: str = "USD"
    is_demo: bool = True
    spread_points: float = 12.0

    _bars: dict[tuple[str, Timeframe], list[Bar]] = field(default_factory=dict)
    _specs: dict[str, SymbolSpec] = field(default_factory=dict)
    _cursor: int = 0
    _positions: list[PositionInfo] = field(default_factory=list)
    _orders: list[OrderInfo] = field(default_factory=list)
    _deals: list[DealInfo] = field(default_factory=list)
    _next_ticket: int = 1
    # A gateway that refuses to send. Used to prove the reconciliation path
    # blocks correctly without needing a broker that misbehaves on cue.
    send_enabled: bool = True

    # ------------------------------------------------------------------ setup
    def load_bars(self, symbol: str, timeframe: Timeframe, bars: list[Bar]) -> None:
        self._bars[(symbol, timeframe)] = list(bars)
        self._specs.setdefault(symbol, default_spec(symbol))

    def load_synthetic(
        self,
        symbols: tuple[str, ...],
        timeframes: tuple[Timeframe, ...],
        count: int,
        seed: int = 20260806,
    ) -> None:
        """Populate every requested series from one seed.

        The M5 series is generated at full length and the higher timeframes are
        aggregated from it, so H1 and M5 describe the same market rather than
        two unrelated random walks — which they would be if each were generated
        independently, and which would make multi-timeframe alignment
        meaningless.
        """
        base_tf = min(timeframes, key=lambda t: t.seconds)
        for symbol in symbols:
            base_count = count * max(1, max(t.seconds for t in timeframes) // base_tf.seconds)
            base_bars = synthesise_bars(symbol, base_tf, base_count, seed=seed)
            self.load_bars(symbol, base_tf, base_bars)
            for timeframe in timeframes:
                if timeframe == base_tf:
                    continue
                self.load_bars(symbol, timeframe, aggregate(base_bars, base_tf, timeframe))

    def set_cursor(self, index: int) -> None:
        """Advance the replay cursor. ``bars()`` never returns beyond it."""
        self._cursor = max(0, index)

    @property
    def cursor(self) -> int:
        return self._cursor

    def series_length(self, symbol: str, timeframe: Timeframe) -> int:
        return len(self._bars.get((symbol, timeframe), []))

    # -------------------------------------------------------- MarketGateway
    def ensure_connected(self) -> bool:
        """No-op. An offline gateway has nothing to attach to.

        Present so the worker can call it unconditionally rather than testing
        which kind of gateway it holds — a check that would go stale the moment
        a third gateway appeared.
        """
        return True

    def reconnect(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return bool(self._bars)

    def server_time(self) -> int:
        latest = 0
        for (_, timeframe), bars in self._bars.items():
            visible = self._visible(bars, timeframe)
            if visible:
                latest = max(latest, visible[-1].time + timeframe.seconds)
        return latest

    def symbols(self) -> list[str]:
        return sorted({symbol for symbol, _ in self._bars})

    def resolve_symbol(self, requested: str) -> str | None:
        available = self.symbols()
        if requested in available:
            return requested
        wanted = requested.upper()
        for symbol in available:
            if symbol.upper() == wanted:
                return symbol
        for symbol in available:
            if symbol.upper().startswith(wanted):
                return symbol
        return None

    def symbol_spec(self, symbol: str) -> SymbolSpec | None:
        return self._specs.get(symbol)

    def _visible(self, bars: list[Bar], timeframe: Timeframe) -> list[Bar]:
        """Bars up to the cursor, scaled so all timeframes advance together.

        The cursor counts base-timeframe steps. A higher timeframe advances
        proportionally slower, which is what keeps H1 from revealing bars that
        M5 has not reached yet — the subtle form of look-ahead that a naive
        replay leaks.
        """
        if self._cursor <= 0:
            return bars
        base_seconds = min((tf.seconds for _, tf in self._bars), default=timeframe.seconds)
        steps = max(1, timeframe.seconds // base_seconds)
        return bars[: max(0, self._cursor // steps)]

    def bars(self, symbol: str, timeframe: Timeframe, count: int) -> list[Bar]:
        series = self._bars.get((symbol, timeframe), [])
        visible = self._visible(series, timeframe)
        return visible[-count:] if count > 0 else visible

    def tick(self, symbol: str) -> Tick | None:
        spec = self._specs.get(symbol)
        if spec is None:
            return None
        for timeframe in sorted(
            {tf for s, tf in self._bars if s == symbol}, key=lambda t: t.seconds
        ):
            visible = self._visible(self._bars[(symbol, timeframe)], timeframe)
            if not visible:
                continue
            last = visible[-1]
            half = self.spread_points * spec.point / 2.0
            return Tick(
                time=last.time + timeframe.seconds,
                bid=last.close - half,
                ask=last.close + half,
                last=last.close,
            )
        return None

    # -------------------------------------------------------- BrokerGateway
    def account(self) -> AccountInfo:
        return AccountInfo(
            login=0,
            server="offline",
            currency=self.currency,
            company="Alikhande Scanner (offline)",
            name="offline session",
            balance=self.balance,
            equity=self.equity,
            margin=0.0,
            margin_free=self.equity,
            leverage=100,
            is_demo=self.is_demo,
            trade_allowed=True,
        )

    def positions(self, magic: int | None = None) -> list[PositionInfo]:
        if magic is None:
            return list(self._positions)
        return [p for p in self._positions if p.magic == magic]

    def orders(self, magic: int | None = None) -> list[OrderInfo]:
        if magic is None:
            return list(self._orders)
        return [o for o in self._orders if o.magic == magic]

    def history_orders(self, since: int, until: int, magic: int | None = None) -> list[OrderInfo]:
        return [
            o
            for o in self._orders
            if since <= o.time_setup <= until and (magic is None or o.magic == magic)
        ]

    def history_deals(self, since: int, until: int, magic: int | None = None) -> list[DealInfo]:
        return [
            d
            for d in self._deals
            if since <= d.time <= until and (magic is None or d.magic == magic)
        ]

    def calc_profit(
        self, symbol: str, direction: int, volume: float, price_open: float, price_close: float
    ) -> float | None:
        """Value the move through tick size and tick value.

        The real MT5 adapter delegates this to the broker. Here it is computed,
        which is correct for the synthetic specs and *approximate* for anything
        involving a currency conversion the offline gateway does not model. The
        backtest report states this.
        """
        spec = self._specs.get(symbol)
        if spec is None or spec.tick_size <= 0.0 or spec.tick_value <= 0.0:
            return None
        sign = 1.0 if direction == int(Direction.LONG) else -1.0
        ticks = (price_close - price_open) / spec.tick_size
        return ticks * spec.tick_value * volume * sign

    def calc_margin(self, symbol: str, direction: int, volume: float, price: float) -> float | None:
        spec = self._specs.get(symbol)
        if spec is None or spec.contract_size <= 0.0:
            return None
        return volume * spec.contract_size * price / 100.0  # assumes 1:100

    def check_order(self, request: OrderRequest) -> tuple[bool, int, str]:
        spec = self._specs.get(request.symbol)
        if spec is None:
            return False, 10013, "unknown symbol"
        if request.volume < spec.volume_min or request.volume > spec.volume_max:
            return False, 10014, "invalid volume"
        return True, 0, "offline check"

    def send_order(self, request: OrderRequest) -> OrderResult:
        """Fill immediately at the requested price.

        Refuses on a non-demo account independently of the execution engine's
        own refusal — the offline gateway mirrors the MT5 adapter's structure so
        the safety property is the same in both, and a test that proves it for
        one is proving the shape both implement.
        """
        if not self.is_demo:
            return OrderResult(ok=False, retcode=10017, comment="REAL_ACCOUNT_BLOCKED")
        if not self.send_enabled:
            return OrderResult(ok=False, retcode=10031, comment="no connection (simulated)")

        ticket = self._next_ticket
        self._next_ticket += 1
        now = self.server_time()

        self._positions.append(
            PositionInfo(
                ticket=ticket,
                symbol=request.symbol,
                magic=request.magic,
                position_id=ticket,
                direction=request.direction,
                volume=request.volume,
                price_open=request.price,
                stop_loss=request.stop_loss,
                take_profit=request.take_profit,
                time=now,
            )
        )
        self._deals.append(
            DealInfo(
                ticket=ticket,
                order=ticket,
                position_id=ticket,
                symbol=request.symbol,
                magic=request.magic,
                entry=0,  # IN
                volume=request.volume,
                price=request.price,
                time=now,
            )
        )
        return OrderResult(
            ok=True,
            retcode=RETCODE_DONE,
            order=ticket,
            deal=ticket,
            request_id=ticket,
            volume=request.volume,
            price=request.price,
            comment="offline fill",
        )

    def close_position(self, position_id: int, price: float, profit: float) -> None:
        """Close a synthetic position, emitting the OUT deal.

        Used by the backtest to make the broker's history agree with what the
        outcome tracker decided, so reconciliation is exercised too rather than
        bypassed.
        """
        remaining = []
        for position in self._positions:
            if position.position_id != position_id:
                remaining.append(position)
                continue
            ticket = self._next_ticket
            self._next_ticket += 1
            self._deals.append(
                DealInfo(
                    ticket=ticket,
                    order=ticket,
                    position_id=position_id,
                    symbol=position.symbol,
                    magic=position.magic,
                    entry=1,  # OUT
                    volume=position.volume,
                    price=price,
                    profit=profit,
                    time=self.server_time(),
                )
            )
        self._positions = remaining


def aggregate(bars: list[Bar], source: Timeframe, target: Timeframe) -> list[Bar]:
    """Roll ``source`` bars up into ``target`` bars.

    Groups by the target period boundary rather than by a fixed count, so a gap
    in the source (a weekend, a missing session) produces a gap rather than a
    silently mis-bucketed bar.
    """
    if target.seconds <= source.seconds:
        return list(bars)

    out: list[Bar] = []
    bucket: list[Bar] = []
    bucket_key: int | None = None

    for bar in bars:
        key = bar.time - (bar.time % target.seconds)
        if bucket_key is None:
            bucket_key = key
        if key != bucket_key:
            if bucket:
                out.append(_merge(bucket, bucket_key))
            bucket = []
            bucket_key = key
        bucket.append(bar)

    if bucket and bucket_key is not None:
        out.append(_merge(bucket, bucket_key))
    return out


def _merge(bucket: list[Bar], time: int) -> Bar:
    return Bar(
        time=time,
        open=bucket[0].open,
        high=max(b.high for b in bucket),
        low=min(b.low for b in bucket),
        close=bucket[-1].close,
        tick_volume=sum(b.tick_volume for b in bucket),
    )
