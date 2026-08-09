"""Plain data carried between layers.

A port of ``Domain/Models.mqh``. No behaviour lives here; engines own the logic
and these carry the shape. Everything is a dataclass with defaults so a partly
populated record is still a valid object — the MQL5 build relied on
``ZeroMemory`` for the same guarantee.

``Bar`` and ``Tick`` are new: MQL5 had ``MqlRates`` and ``MqlTick`` built in,
and the pure core needs its own so it never has to import a gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import (
    AssetClass,
    DataState,
    Direction,
    ExecState,
    NewsSource,
    NewsState,
    Regime,
    RuntimeKind,
    SetupType,
    SignalState,
    SpreadState,
    Timeframe,
    TrendClass,
    ZoneRelation,
    ZoneType,
)


@dataclass(frozen=True)
class Bar:
    """One OHLC bar. ``time`` is the bar's OPEN time, as MetaTrader reports it."""

    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    spread: int = 0
    real_volume: int = 0


@dataclass(frozen=True)
class Tick:
    time: int
    bid: float
    ask: float
    last: float = 0.0
    volume: int = 0


@dataclass
class SymbolSpec:
    """Contract specification. Every field here feeds position sizing."""

    symbol: str = ""
    digits: int = 0
    point: float = 0.0
    tick_size: float = 0.0
    tick_value: float = 0.0
    contract_size: float = 0.0
    volume_min: float = 0.0
    volume_max: float = 0.0
    volume_step: float = 0.0
    stops_level: int = 0
    freeze_level: int = 0
    trade_mode: int = 0
    currency_base: str = ""
    currency_profit: str = ""
    currency_margin: str = ""
    fingerprint: str = ""
    ready: bool = False


@dataclass
class SymbolSnapshot:
    requested_symbol: str = ""
    symbol: str = ""
    bid: float = 0.0
    ask: float = 0.0
    point: float = 0.0
    digits: int = 0
    spread_points: float = 0.0
    spread_ratio: float = 0.0
    spread_percentile: float = 0.0
    tick_time: int = 0
    spread_state: SpreadState = SpreadState.NO_TICK
    data_state: DataState = DataState.UNINITIALIZED


@dataclass
class TrendResult:
    timeframe: Timeframe = Timeframe.H1
    direction_score: float = 0.0  # -100..+100
    strength: float = 0.0  # 0..100, magnitude only
    trend_class: TrendClass = TrendClass.NEUTRAL
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    adx: float = 0.0
    atr: float = 0.0
    atr_ratio: float = 0.0
    # Wall-clock time at which this information first became knowable — the
    # close of the analysed bar, never its open. Guards against look-ahead.
    available_information_time: int = 0
    valid: bool = False


@dataclass
class Zone:
    id: str = ""
    type: ZoneType = ZoneType.DEMAND
    timeframe: Timeframe = Timeframe.H1
    low: float = 0.0
    high: float = 0.0
    center: float = 0.0
    touches: int = 0
    quality: float = 0.0  # 0..100
    pivot_time: int = 0
    confirmation_time: int = 0
    broken: bool = False
    valid: bool = False


@dataclass
class RegimeResult:
    regime: Regime = Regime.UNKNOWN
    confidence: float = 0.0  # 0..100
    reason: str = ""
    valid: bool = False


@dataclass(frozen=True)
class ScoreComponent:
    """One line of the score breakdown.

    The dashboard shows these so it can explain *why* a score is what it is
    instead of presenting a bare number the operator has to take on faith.
    """

    component: str
    contribution: float


@dataclass
class SignalCandidate:
    signal_id: str = ""
    symbol: str = ""
    direction: Direction = Direction.NONE
    setup: SetupType = SetupType.NONE
    state: SignalState = SignalState.NONE

    preferred_entry: float = 0.0
    entry_low: float = 0.0
    entry_high: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    demand_relation: ZoneRelation = ZoneRelation.UNAVAILABLE
    supply_relation: ZoneRelation = ZoneRelation.UNAVAILABLE

    long_score: float = 0.0  # rule score, NOT a probability
    short_score: float = 0.0
    long_components: list[ScoreComponent] = field(default_factory=list)
    short_components: list[ScoreComponent] = field(default_factory=list)
    validation_codes: list[str] = field(default_factory=list)
    hard_blocked: bool = False

    # Outcome-derived statistics. ``has_historical_estimate`` stays false until
    # a real, sufficiently large outcome sample exists; the UI must never
    # render a probability while it is false.
    has_historical_estimate: bool = False
    historical_win_rate: float = 0.0
    sample_size: int = 0
    confidence_low: float = 0.0
    confidence_high: float = 0.0

    regime: Regime = Regime.UNKNOWN
    confirmation_bar_time: int = 0
    creation_time: int = 0
    expires_at: int = 0

    rule_version: str = ""
    scoring_version: str = ""
    parameter_hash: str = ""
    broker_spec_hash: str = ""

    @property
    def components(self) -> list[ScoreComponent]:
        """The breakdown for the side that actually won, or the empty list."""
        if self.direction == Direction.LONG:
            return self.long_components
        if self.direction == Direction.SHORT:
            return self.short_components
        return []

    def reasons_text(self) -> str:
        return ";".join(f"{c.component}{c.contribution:+.0f}" for c in self.components)

    def codes_text(self) -> str:
        return ";".join(self.validation_codes)


@dataclass
class TradePlan:
    plan_id: str = ""
    signal_id: str = ""
    symbol: str = ""
    direction: Direction = Direction.NONE
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_percent: float = 0.0
    risk_amount: float = 0.0
    actual_risk_amount: float = 0.0
    lot_size: float = 0.0
    margin_required: float = 0.0
    preview_bid: float = 0.0
    preview_ask: float = 0.0
    created_at: int = 0
    expires_at: int = 0
    max_drift_points: float = 0.0
    minimum_rr: float = 0.0
    validation_codes: list[str] = field(default_factory=list)
    valid: bool = False

    def codes_text(self) -> str:
        return ";".join(self.validation_codes)


@dataclass
class ExecutionRecord:
    execution_id: str = ""
    plan_id: str = ""
    signal_id: str = ""
    symbol: str = ""
    state: ExecState = ExecState.IDLE
    request_id: int = 0
    order_ticket: int = 0
    deal_ticket: int = 0
    position_id: int = 0
    requested_volume: float = 0.0
    filled_volume: float = 0.0
    retcode: int = 0
    message: str = ""
    created_at: int = 0
    updated_at: int = 0
    terminal: bool = False


@dataclass
class Outcome:
    signal_id: str = ""
    # TP | SL | EXPIRED | INVALIDATED | NOT_FILLED | AMBIGUOUS
    result: str = ""
    realized_r: float = 0.0  # realised result in R multiples
    mfe_r: float = 0.0  # maximum favourable excursion, in R
    mae_r: float = 0.0  # maximum adverse excursion, in R
    closed_at: int = 0


@dataclass
class RiskState:
    """Persisted guard state.

    Without this, a restart mid-drawdown silently resets the peak-equity
    baseline and the drawdown guard stops guarding — which was v1.1.0's bug.
    """

    day_key: int = 0
    day_start_equity: float = 0.0
    peak_equity: float = 0.0
    consecutive_losses: int = 0
    daily_risk_used_pct: float = 0.0
    updated_at: int = 0


@dataclass
class ExposureSummary:
    open_risk_pct: float = 0.0
    symbol_risk_pct: float = 0.0
    currency_risk_pct: float = 0.0
    asset_class_risk_pct: float = 0.0
    dominant_currency: str = ""
    open_positions: int = 0
    # Positions whose worst case cannot be computed (no stop, or an unpriceable
    # symbol). These are NOT zero-risk. While any exist the measured
    # percentages are lower bounds and no new risk may be admitted.
    unbounded_positions: int = 0
    unbounded_symbols: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AccountInfo:
    login: int = 0
    server: str = ""
    currency: str = ""
    company: str = ""
    name: str = ""
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    margin_free: float = 0.0
    leverage: int = 0
    # The single most important field in this file. ``True`` only when the
    # broker reports a demo account; everything execution-related keys off it.
    is_demo: bool = False
    trade_allowed: bool = False


@dataclass(frozen=True)
class PositionInfo:
    ticket: int = 0
    symbol: str = ""
    magic: int = 0
    position_id: int = 0
    direction: Direction = Direction.NONE
    volume: float = 0.0
    price_open: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    profit: float = 0.0
    time: int = 0


@dataclass(frozen=True)
class OrderInfo:
    ticket: int = 0
    symbol: str = ""
    magic: int = 0
    state: str = ""
    volume_initial: float = 0.0
    volume_current: float = 0.0
    price_open: float = 0.0
    time_setup: int = 0


@dataclass(frozen=True)
class DealInfo:
    ticket: int = 0
    order: int = 0
    position_id: int = 0
    symbol: str = ""
    magic: int = 0
    entry: int = 0  # 0 = IN, 1 = OUT, 2 = INOUT, 3 = OUT_BY (MetaTrader coding)
    volume: float = 0.0
    price: float = 0.0
    profit: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    time: int = 0

    @property
    def net_profit(self) -> float:
        return self.profit + self.commission + self.swap


DEAL_ENTRY_IN = 0
DEAL_ENTRY_OUT = 1
DEAL_ENTRY_INOUT = 2
DEAL_ENTRY_OUT_BY = 3


@dataclass(frozen=True)
class OrderRequest:
    """A validated order, ready to send verbatim.

    Built only by ``core.preflight``. The execution engine sends what it is
    given and nothing else, so there is exactly one place where the contents of
    an order are decided.
    """

    symbol: str
    direction: Direction
    volume: float
    price: float
    stop_loss: float
    take_profit: float
    deviation: int
    magic: int
    comment: str


@dataclass(frozen=True)
class OrderResult:
    ok: bool = False
    retcode: int = 0
    order: int = 0
    deal: int = 0
    request_id: int = 0
    volume: float = 0.0
    price: float = 0.0
    comment: str = ""


@dataclass(frozen=True)
class NewsVerdict:
    state: NewsState = NewsState.UNKNOWN
    source: NewsSource = NewsSource.UNAVAILABLE
    event_name: str = ""
    currency: str = ""
    event_time: int = 0
    reason: str = ""


@dataclass(frozen=True)
class RuntimeContext:
    kind: RuntimeKind = RuntimeKind.OFFLINE
    is_production: bool = False
    session_identity: str = ""
    description: str = ""


@dataclass(frozen=True)
class ArmedIntent:
    armed: bool = False
    plan_id: str = ""
    signal_id: str = ""
    symbol: str = ""
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    lot_size: float = 0.0
    armed_at: int = 0
    expires_at: int = 0


def asset_class_of(symbol: str) -> AssetClass:
    """Classify a symbol by name.

    Lives here rather than in the portfolio module because both the risk layer
    and the UI need it, and a second copy would drift.
    """
    upper = symbol.upper()
    if any(metal in upper for metal in ("XAU", "XAG", "XPT", "XPD")):
        return AssetClass.METAL
    if any(crypto in upper for crypto in ("BTC", "ETH", "LTC", "XRP")):
        return AssetClass.CRYPTO
    base, quote = currency_legs(symbol)
    if len(base) == 3 and len(quote) == 3:
        return AssetClass.FX
    return AssetClass.UNKNOWN


def currency_legs(symbol: str) -> tuple[str, str]:
    """Split a symbol into its currency legs, tolerating broker decoration.

    Handles the shapes seen in the wild: ``EURUSD``, ``EURUSD_o``, ``#GBPJPY``,
    ``EURUSD.m``. Returns ``("", "")`` when the name is not a six-letter pair.
    """
    clean = symbol.strip()
    if clean.startswith("#"):
        clean = clean[1:]
    for separator in ("_", ".", "-"):
        index = clean.find(separator)
        if index >= 6:
            clean = clean[:index]
            break
    if len(clean) >= 6 and clean[:6].isalpha():
        return clean[:3].upper(), clean[3:6].upper()
    return "", ""
