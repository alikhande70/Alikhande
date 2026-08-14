"""Domain enumerations.

A direct port of ``Domain/Enums.mqh``. The integer values are pinned because
they are persisted: ``direction`` and ``setup`` go into the database as
integers, and changing a member's value silently reinterprets every stored row.
"""

from __future__ import annotations

from enum import Enum, IntEnum


class DataState(IntEnum):
    UNINITIALIZED = 0
    SELECTING = 1
    DOWNLOADING = 2
    SYNCHRONIZING = 3
    READY = 4
    STALE = 5
    ERROR = 6


class TrendClass(IntEnum):
    STRONG_BEARISH = -3
    BEARISH = -2
    WEAK_BEARISH = -1
    NEUTRAL = 0
    WEAK_BULLISH = 1
    BULLISH = 2
    STRONG_BULLISH = 3


class Direction(IntEnum):
    NONE = 0
    LONG = 1
    SHORT = -1


class ZoneType(IntEnum):
    """Zones are typed at construction.

    v1.1.0 merged swing highs and swing lows into a single untyped band, which
    inflated the touch count that feeds zone quality, which feeds the score.
    Supply and demand are tracked separately.
    """

    SUPPLY = 0  # formed by swing highs
    DEMAND = 1  # formed by swing lows


class ZoneRelation(IntEnum):
    """Where price sits relative to a zone.

    An explicit three-way relation rather than a pair of booleans. The boolean
    form quietly conflates two different situations — "price is not inside the
    zone" and "there is no usable zone" — and that conflation is what produced
    v1.1.0's blindness at the entry trigger. Making UNAVAILABLE its own answer
    forces every caller to decide what to do about it.
    """

    UNAVAILABLE = 0
    BELOW = 1
    INSIDE = 2
    ABOVE = 3


class SetupType(IntEnum):
    NONE = 0
    TREND_PULLBACK = 1
    SUPPORT_REJECTION = 2
    RESISTANCE_REJECTION = 3
    BREAKOUT_RETEST = 4  # reserved; never emitted until it has its own tests


class Regime(IntEnum):
    UNKNOWN = 0
    TREND_UP = 1
    TREND_DOWN = 2
    RANGE = 3
    VOLATILE = 4
    QUIET = 5
    ILLIQUID = 6


class SpreadState(IntEnum):
    WARMING_UP = 0
    NORMAL = 1
    ELEVATED = 2
    HIGH = 3
    EXTREME = 4
    STALE = 5
    NO_TICK = 6


class SignalState(IntEnum):
    """A signal is never shown once and forgotten.

    Every candidate walks this machine and every transition is persisted, which
    is what makes outcome statistics possible later.
    """

    NONE = 0
    CANDIDATE = 1  # score cleared threshold, not yet actionable
    CONFIRMED = 2  # setup qualified and structurally valid
    PREVIEWED = 3  # shown to the operator with a sized plan
    ACTIVE = 4  # a position exists against this signal
    TP = 5
    SL = 6
    EXPIRED = 7  # TTL elapsed without action
    INVALIDATED = 8  # structure broke before entry
    NOT_FILLED = 9
    AMBIGUOUS = 10  # outcome could not be reconciled — needs a human


class ExecState(IntEnum):
    IDLE = 0
    SUBMITTING = 1
    ACCEPTED = 2
    PARTIALLY_FILLED = 3
    FILLED = 4
    POSITION_ACTIVE = 5
    REJECTED = 6
    CANCELLED = 7
    UNKNOWN = 8  # sent, no confirmation — must be reconciled
    RECONCILING = 9
    COMPLETED = 10


class RunMode(IntEnum):
    """Operating mode.

    Real trading is not reachable in this line at all: there is no enum member
    for it, so no configuration mistake can select it. The execution engine
    additionally refuses any non-demo account with a hard return, and the MT5
    adapter refuses again independently — three separate refusals sharing no
    code path.
    """

    ALERT_ONLY = 0  # scan and report; no order ever leaves the app
    SHADOW = 1  # full plan + preflight, logged as if sent, never sent
    DEMO_CONFIRM = 2  # demo accounts only, after arm AND confirm


class AssetClass(IntEnum):
    UNKNOWN = 0
    FX = 1
    METAL = 2
    INDEX = 3
    CRYPTO = 4
    STOCK = 5


class NewsSource(IntEnum):
    LIVE = 0  # a calendar answered
    TEST_DATA = 1  # supplied dataset
    UNAVAILABLE = 2  # no calendar could be consulted


class NewsState(IntEnum):
    CLEAR = 0  # consulted a source; nothing relevant in the window
    BLOCKED = 1  # consulted a source; a relevant event is in the window
    UNKNOWN = 2  # no source could be consulted — NOT the same as clear


class RuntimeKind(IntEnum):
    """Which execution environment the app is running in.

    The MQL5 build distinguished TERMINAL / TESTER / OPTIMIZATION because a
    backtest and an optimization sweep both write records that look identical
    to real ones. The desktop build has the same problem with different names:
    a live MT5 session, a replay over recorded bars, and a synthetic offline
    demo all produce signals, and mixing them in one database would silently
    contaminate any win rate computed later.
    """

    LIVE = 0  # attached to a running MT5 terminal — the only production context
    REPLAY = 1  # deterministic replay over recorded or synthetic bars
    OFFLINE = 2  # no gateway at all; UI exploration only


class Timeframe(Enum):
    """Timeframes, carrying their own length in seconds.

    Named to match MetaTrader's periods so the MT5 adapter can map them
    directly, and carrying ``seconds`` so the pure core never has to ask a
    gateway how long a bar is.
    """

    M1 = ("M1", 60)
    M5 = ("M5", 300)
    M15 = ("M15", 900)
    M30 = ("M30", 1800)
    H1 = ("H1", 3600)
    H4 = ("H4", 14400)
    D1 = ("D1", 86400)

    def __init__(self, label: str, seconds: int) -> None:
        self.label = label
        self.seconds = seconds

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.label


# --------------------------------------------------------------------- names
#
# Display names live beside their enums so no call site has to invent one, and
# so a renamed member cannot leave a stale string behind in the UI.

TREND_CLASS_NAMES: dict[TrendClass, str] = {
    TrendClass.STRONG_BEARISH: "Strong Bearish",
    TrendClass.BEARISH: "Bearish",
    TrendClass.WEAK_BEARISH: "Weak Bearish",
    TrendClass.NEUTRAL: "Neutral",
    TrendClass.WEAK_BULLISH: "Weak Bullish",
    TrendClass.BULLISH: "Bullish",
    TrendClass.STRONG_BULLISH: "Strong Bullish",
}

REGIME_NAMES: dict[Regime, str] = {
    Regime.UNKNOWN: "Unknown",
    Regime.TREND_UP: "Trend Up",
    Regime.TREND_DOWN: "Trend Down",
    Regime.RANGE: "Range",
    Regime.VOLATILE: "Volatile",
    Regime.QUIET: "Quiet",
    Regime.ILLIQUID: "Illiquid",
}

SETUP_NAMES: dict[SetupType, str] = {
    SetupType.NONE: "—",
    SetupType.TREND_PULLBACK: "Trend Pullback",
    SetupType.SUPPORT_REJECTION: "Support Rejection",
    SetupType.RESISTANCE_REJECTION: "Resistance Rejection",
    SetupType.BREAKOUT_RETEST: "Breakout Retest",
}

DIRECTION_NAMES: dict[Direction, str] = {
    Direction.NONE: "—",
    Direction.LONG: "LONG",
    Direction.SHORT: "SHORT",
}

SPREAD_STATE_NAMES: dict[SpreadState, str] = {
    SpreadState.WARMING_UP: "Warming up",
    SpreadState.NORMAL: "Normal",
    SpreadState.ELEVATED: "Elevated",
    SpreadState.HIGH: "High",
    SpreadState.EXTREME: "Extreme",
    SpreadState.STALE: "Stale",
    SpreadState.NO_TICK: "No tick",
}


def zone_relation_name(relation: ZoneRelation) -> str:
    return relation.name


def signal_state_name(state: SignalState) -> str:
    return state.name


def exec_state_name(state: ExecState) -> str:
    return state.name


def news_state_name(state: NewsState) -> str:
    return state.name


def news_source_name(source: NewsSource) -> str:
    return source.name


def runtime_kind_name(kind: RuntimeKind) -> str:
    return kind.name
