"""The scan orchestrator.

Headless on purpose: it owns no Qt objects and can be driven by a test, by the
backtest replay, or by the UI worker thread. The UI reads the snapshot this
produces and never reaches past it into a gateway.

The pass structure follows the structural/live split:

* **Structure** is rebuilt only when a closed bar changed on any analysed
  timeframe. It is the expensive half — indicator maths over hundreds of bars.
* **Live** runs every pass against the current quote. It is arithmetic over
  cached structure, so it stays cheap enough to run continuously.

That split is what makes a displayed signal never older than the tick it is
shown with, which was v1.1.0's most dangerous defect.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import AppConfig
from ..core.arming import IntentArming
from ..core.calendar_gate import CalendarGate
from ..core.enums import (
    DataState,
    Direction,
    ExecState,
    NewsState,
    RunMode,
    RuntimeKind,
    SignalState,
    SpreadState,
    Timeframe,
)
from ..core.environment import Environment, account_verdict, capabilities, send_refusal
from ..core.execution import BrokerTruth, DealLedger, ExecutionEngine
from ..core.features import extract as extract_features
from ..core.guards import AccountRiskGuard, TradeGuards
from ..core.journal import Journal
from ..core.lifecycle import is_terminal
from ..core.order_errors import ErrorTally
from ..core.models import (
    AccountInfo,
    Bar,
    ExecutionRecord,
    ExposureSummary,
    NewsVerdict,
    Outcome,
    OrderInfo,
    PositionInfo,
    RiskState,
    RuntimeContext,
    SignalCandidate,
    SymbolSnapshot,
    SymbolSpec,
    TradePlan,
    Zone,
)
from ..core.outcomes import OutcomeTracker
from ..core.ports import BrokerGateway
from ..core.risk import RiskPlanner
from ..core.signals import SignalEngine, StructuralContext, evidence_signal_id
from ..core.spread import SpreadTracker
from ..core.statistics import Statistics
from ..version import RULE_VERSION, SCORING_VERSION, VERSION
from ..core.hashing import fnv1a64

ANALYSED_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.H4,
    Timeframe.H1,
    Timeframe.M15,
    Timeframe.M5,
)


@dataclass
class SymbolView:
    """Everything the UI needs about one symbol, in one object."""

    requested: str = ""
    symbol: str = ""
    resolved: bool = False
    snapshot: SymbolSnapshot = field(default_factory=SymbolSnapshot)
    spec: SymbolSpec | None = None
    signal: SignalCandidate | None = None
    plan: TradePlan | None = None
    news: NewsVerdict = field(default_factory=NewsVerdict)
    news_blocks: bool = False
    structure_built_at: int = 0
    last_error: str = ""
    # Carried so the detail view can DRAW the structure rather than assert it.
    # A scanner whose whole thesis is "price is inside a demand zone" has to let
    # the operator see that and disagree; without the bars there is nothing to
    # check the claim against.
    bars: list[Bar] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    regime_reason: str = ""


@dataclass
class EngineSnapshot:
    """An immutable-enough view handed to the UI thread once per pass."""

    now: int = 0
    connected: bool = False
    runtime: RuntimeContext = field(default_factory=RuntimeContext)
    account: AccountInfo | None = None
    mode: RunMode = RunMode.ALERT_ONLY
    symbols: list[SymbolView] = field(default_factory=list)
    exposure_open_pct: float = 0.0
    guard_codes: list[str] = field(default_factory=list)
    may_trade: bool = True
    execution_state: str = "IDLE"
    execution_message: str = ""
    requires_manual_review: bool = False
    armed_symbol: str = ""
    armed_seconds: int = 0
    news_blind: bool = False
    passes: int = 0
    last_pass_ms: float = 0.0

    # ---- environment -------------------------------------------------------
    # Carried on the snapshot rather than read from the engine by the UI, so
    # what is drawn on screen is the environment the pass actually ran under.
    # Reading it live would let a switch mid-pass paint a production banner
    # over demo results.
    environment: str = Environment.DEMO
    #: ``good`` / ``warning`` / ``critical`` / ``unknown`` — does the attached
    #: account match the declared environment?
    account_severity: str = "unknown"
    account_code: str = "ACCOUNT_UNKNOWN"
    #: Empty when an order could be sent; a reason code otherwise. The UI shows
    #: this verbatim rather than deciding for itself whether sending is possible.
    send_lock: str = ""
    # Complete read model. The GUI has no engine/repository/gateway reference;
    # these values are deep-copied after the pass and never mutated again.
    # Empty collections mean "authoritatively empty" only while the matching
    # flag is true. A failed broker read is UNKNOWN, never zero exposure.
    positions_known: bool = True
    orders_known: bool = True
    positions: list[PositionInfo] = field(default_factory=list)
    working_orders: list[OrderInfo] = field(default_factory=list)
    exposure: ExposureSummary = field(default_factory=ExposureSummary)
    guard_state: RiskState = field(default_factory=RiskState)
    execution: ExecutionRecord = field(default_factory=ExecutionRecord)
    execution_unresolved: bool = False
    journal_entries: list[object] = field(default_factory=list)
    order_errors: ErrorTally = field(default_factory=ErrorTally)
    outcome_summary: dict[str, float] = field(default_factory=dict)
    opportunities: list[object] = field(default_factory=list)
    persistence_ready: bool = False


class ScanEngine:
    def __init__(
        self,
        gateway: BrokerGateway,
        config: AppConfig | None = None,
        *,
        runtime: RuntimeContext | None = None,
        journal: Journal | None = None,
        repositories=None,
        calendar: CalendarGate | None = None,
        run_id: str = "",
        environment: str = Environment.DEMO,
    ) -> None:
        self._gateway = gateway
        self._config = config or AppConfig()
        self._runtime = runtime or RuntimeContext()
        self._journal = journal or Journal()
        self._repo = repositories
        self._run_id = run_id
        self._environment = Environment.parse(environment)

        self._signals = SignalEngine(self._config)
        self._risk = RiskPlanner(self._config)
        self._statistics = Statistics(repositories, self._config.statistics)
        self._guards = TradeGuards()
        self._account_guard = AccountRiskGuard(self._config.risk)
        self._arming = IntentArming(self._config.execution, self._journal)
        ledger = DealLedger(self._repo.record_deal_once) if self._repo is not None else DealLedger()
        if self._repo is not None:
            ledger.load(self._repo.known_deal_tickets())
        self._execution = ExecutionEngine(
            self._config, self._journal, ledger, environment=self._environment
        )
        self._calendar = calendar or CalendarGate(None, self._config.news, self._journal)
        self._outcomes = OutcomeTracker()

        self._mode = RunMode.ALERT_ONLY
        self._contexts: dict[str, StructuralContext] = {}
        self._spread: dict[str, SpreadTracker] = {}
        self._specs: dict[str, SymbolSpec] = {}
        self._resolved: dict[str, str] = {}
        self._last_bar_time: dict[str, int] = {}
        self._views: dict[str, SymbolView] = {}
        self._passes = 0
        self._cursor = 0  # round-robin position for slicing
        # One coherent account-state read is shared by scanning, risk and the
        # UI snapshot for each pass. Re-reading in each consumer could combine
        # mutually inconsistent moments or turn one failed read into an empty
        # list in only part of the interface.
        self._all_positions: list[PositionInfo] = []
        self._all_orders: list[OrderInfo] = []
        self._own_positions_cache: list[PositionInfo] = []
        self._own_orders_cache: list[OrderInfo] = []
        self._positions_known = False
        self._orders_known = False

        if self._repo is not None:
            self._execution.set_persistence(self._repo.save_execution)

    # ------------------------------------------------------------ properties
    @property
    def mode(self) -> RunMode:
        return self._mode

    @property
    def environment(self) -> str:
        return self._environment

    @property
    def execution(self) -> ExecutionEngine:
        return self._execution

    @property
    def arming(self) -> IntentArming:
        return self._arming

    @property
    def outcomes(self) -> OutcomeTracker:
        return self._outcomes

    @property
    def journal(self) -> Journal:
        return self._journal

    @property
    def guard_state(self):
        return self._account_guard.state

    def server_time(self, fallback: int = 0) -> int:
        """Broker server time, or ``fallback`` when the gateway cannot say.

        Deliberately not the local clock as a silent substitute: every TTL, news
        window and staleness check in the system is measured against the
        server's idea of now, so a caller that needs a clock has to decide for
        itself what to do when there isn't one.
        """
        try:
            return self._gateway.server_time()
        except Exception:
            return fallback

    def set_mode(self, mode: RunMode, now: int) -> tuple[bool, str]:
        """Change run mode.

        A mode that can send is refused unless the account is demo and
        persistence exists. Refusing here rather than at submit time means the
        UI can never present an armed control that would fail on the click.

        The environment is consulted first and separately. It refuses on what
        was *declared* rather than on what the terminal reported, so a
        production session cannot select a sending mode even in the case the
        account checks below cannot see — a broker misreporting the demo flag,
        or a terminal relogged into a different account mid-session.
        """
        caps = capabilities(self._environment)
        if not caps.may_use(mode):
            return False, f"MODE_NOT_AVAILABLE_IN_{caps.environment}"

        if mode != RunMode.ALERT_ONLY:
            account = self._safe_account()
            if account is None:
                return False, "NO_ACCOUNT"
            if mode == RunMode.DEMO_CONFIRM and not account.is_demo:
                return False, "REAL_ACCOUNT_BLOCKED"
        if mode == RunMode.DEMO_CONFIRM and self._repo is None:
            # Without persistence there is no de-duplication across restarts and
            # no durable record of an in-flight order. Sending under those
            # conditions is exactly the situation restart recovery exists for.
            return False, "PERSISTENCE_REQUIRED_FOR_DEMO_EXECUTION"

        self._mode = mode
        self._arming.disarm("MODE_CHANGED", now)
        self._journal.info("MODE_CHANGED", "", f"run mode is now {mode.name}", now)
        return True, ""

    def reconfigure(self, config: AppConfig, now: int) -> tuple[bool, str]:
        """Swap in a new configuration between passes.

        What gets rebuilt is deliberately narrow: scoring, risk planning, the
        statistics gate and the account guard. The execution engine and the
        arming state machine are **not** rebuilt, because they hold the
        identity of an in-flight order and a live arming window — replacing
        either mid-flight would orphan a real order in the terminal while the
        application forgot it existed.

        For the same reason a change is refused outright while an execution is
        unresolved or an intent is armed. A refusal the operator can see and
        retry is far better than a reconfiguration that lands halfway.

        Symbols are not applied here: the resolved-symbol map, the structural
        contexts and the spread trackers are all keyed on the set
        ``initialize`` established. Changing that takes a restart, and the
        settings view says so.
        """
        if self._execution.has_unresolved():
            return False, "EXECUTION_UNRESOLVED"
        if self._arming.is_armed(now):
            return False, "INTENT_ARMED"

        # Symbols come from the running config rather than the incoming one, so
        # a preset change cannot drop a symbol the engine already holds state
        # for.
        self._config = config.with_symbols(self._config.symbols)
        self._signals = SignalEngine(self._config)
        self._risk = RiskPlanner(self._config)
        self._statistics = Statistics(self._repo, self._config.statistics)
        # Changing a preset must not reset the persisted drawdown/daily-loss
        # baseline. Rebuild the policy around an exact copy of the state that
        # was in force immediately before this action.
        import copy

        previous_guard = copy.deepcopy(self._account_guard.state)
        self._account_guard = AccountRiskGuard(self._config.risk)
        account = self._safe_account()
        self._account_guard.initialize(
            account.equity if account is not None else 0.0, now, previous_guard
        )
        self._journal.info(
            "CONFIG_CHANGED",
            "",
            f"threshold={self._config.scoring.score_threshold:.0f} "
            f"rr={self._config.risk.minimum_risk_reward:.2f} "
            f"risk={self._config.risk.risk_percent:.2f}",
            now,
        )
        return True, ""

    # ---------------------------------------------------------------- startup
    def initialize(self, now: int) -> None:
        """Resolve symbols, load specs, restore state."""
        self._calendar.apply_runtime_policy(self._runtime, now)
        self._ensure_run(now)

        for requested in self._config.symbols:
            view = SymbolView(requested=requested)
            resolved = None
            try:
                resolved = self._gateway.resolve_symbol(requested)
            except Exception as error:
                view.last_error = str(error)

            if resolved is None:
                view.last_error = view.last_error or "SYMBOL_NOT_FOUND"
                self._journal.warn(
                    "SYMBOL_UNRESOLVED", requested, "no broker symbol matched", now
                )
            else:
                view.symbol = resolved
                view.resolved = True
                self._resolved[requested] = resolved
                self._spread[resolved] = SpreadTracker(self._config.scan)
                spec = self._gateway.symbol_spec(resolved)
                if spec is not None:
                    self._register_spec(spec, now)
                    view.spec = spec
            self._views[requested] = view

        account = self._safe_account()
        # Establish a real exposure answer before any direct API caller can
        # arm. The worker performs a pass before consuming actions, but the
        # engine contract itself should be safe without relying on that caller.
        self._refresh_broker_state(now)
        equity = account.equity if account else 0.0
        stored = self._repo.load_risk_state() if self._repo is not None else None
        self._account_guard.initialize(equity, now, stored)

        if self._repo is not None:
            recovery = self._repo.load_unresolved_execution()
            awaiting_outcome = False
            if recovery is None:
                recovery = self._repo.load_execution_awaiting_outcome()
                awaiting_outcome = recovery is not None
                if recovery is not None:
                    # A completed fill needs exact deals to reconstruct prices,
                    # P/L and close reason. A rejection/cancellation already is
                    # its own complete, non-scorable broker disposition.
                    if (
                        recovery.state == ExecState.COMPLETED
                        and recovery.mode != RunMode.SHADOW
                    ):
                        recovery.terminal = False
            shadow_disposition = bool(
                awaiting_outcome
                and recovery is not None
                and recovery.state == ExecState.COMPLETED
                and recovery.mode == RunMode.SHADOW
            )
            retain_disposition = bool(
                awaiting_outcome
                and recovery is not None
                and (
                    recovery.state in (ExecState.REJECTED, ExecState.CANCELLED)
                    or shadow_disposition
                )
            )
            self._execution.recover_after_restart(
                recovery, now, reconcile=not retain_disposition
            )
            if recovery is not None:
                if shadow_disposition:
                    self._apply_shadow_outcome(now)
                elif retain_disposition:
                    self._apply_broker_truth(
                        BrokerTruth(
                            resolved=True,
                            state=recovery.state,
                            terminal=True,
                            source="PERSISTED_SEND_RESULT",
                            detail=recovery.message,
                        ),
                        now,
                    )
                else:
                    persisted_truth = self._execution.reconcile_persisted_deals(
                        self._repo.deals_for_execution(recovery.execution_id), now
                    )
                    if persisted_truth is not None and persisted_truth.terminal:
                        self._apply_broker_truth(persisted_truth, now)
            self._journal.extend(self._repo.recent_events(100))

    def refresh_gateway_state(self, now: int) -> None:
        """Rebuild broker metadata after a successful worker-owned reconnect.

        An initial attach can fail while the terminal is still starting.  The
        old reconnect path repaired the IPC handle but left every symbol marked
        unresolved forever because :meth:`initialize` is intentionally run only
        once.  Refresh only the connection-derived metadata here; execution and
        recovery state remain untouched.
        """
        for requested, view in self._views.items():
            if not view.resolved:
                try:
                    resolved = self._gateway.resolve_symbol(requested)
                except Exception as error:
                    view.last_error = str(error)
                    continue
                if resolved is None:
                    view.last_error = "SYMBOL_NOT_FOUND"
                    continue
                view.symbol = resolved
                view.resolved = True
                view.last_error = ""
                self._resolved[requested] = resolved
                self._spread.setdefault(resolved, SpreadTracker(self._config.scan))

            try:
                spec = self._gateway.symbol_spec(view.symbol)
            except Exception as error:
                view.last_error = f"SPEC_UNAVAILABLE({type(error).__name__})"
                continue
            if spec is None or not spec.ready:
                view.last_error = "NO_SYMBOL_SPEC"
                continue
            self._register_spec(spec, now)
            view.spec = spec

        account = self._safe_account()
        if account is not None and self._account_guard.state.peak_equity <= 0.0:
            stored = self._repo.load_risk_state() if self._repo is not None else None
            self._account_guard.initialize(account.equity, now, stored)
        self._refresh_broker_state(now)
        self._ensure_run(now)

    def _ensure_run(self, now: int) -> None:
        """Create provenance only after a real gateway actually answered."""
        if self._repo is None or self._run_id or not self._safe_connected():
            return
        import uuid

        self._run_id = f"LIVE-{uuid.uuid4().hex.upper()}"
        self._repo.start_run(
            run_id=self._run_id,
            kind=self._runtime.kind.name,
            is_production=self._runtime.is_production,
            app_version=VERSION,
            rule_version=RULE_VERSION,
            scoring_version=SCORING_VERSION,
            parameter_hash=fnv1a64(self._config.parameter_fingerprint_source()),
            symbols=",".join(self._config.symbols),
            started_at=now,
            note=f"declared environment {self._environment}",
        )

    def _register_spec(self, spec: SymbolSpec, now: int) -> None:
        """Store a spec and shout if the broker changed it under us.

        A broker changing a contract's tick value or minimum volume silently
        changes what every previously stored position size meant. Comparing
        fingerprints turns an invisible change into a visible event.
        """
        self._specs[spec.symbol] = spec
        if self._repo is None:
            return
        previous = self._repo.spec_fingerprint(spec.symbol)
        if previous and previous != spec.fingerprint:
            self._journal.warn(
                "SPEC_DRIFT",
                spec.symbol,
                f"contract specification changed ({previous} -> {spec.fingerprint}); "
                "position sizes computed before this point were sized against "
                "different contract terms",
                now,
            )
        self._repo.save_spec(spec, now)

    def _safe_account(self) -> AccountInfo | None:
        try:
            return self._gateway.account()
        except Exception:
            return None

    def _refresh_broker_state(self, now: int) -> None:
        """Read account exposure once and preserve failure as UNKNOWN.

        MetaTrader returns an empty tuple when the answer is truly empty and
        ``None`` on failure; the adapter raises for the latter. This layer must
        not undo that distinction by catching the error and returning ``[]``.
        """
        try:
            self._all_positions = list(self._gateway.positions(None))
            self._positions_known = True
        except Exception as error:
            self._all_positions = []
            self._positions_known = False
            self._journal.warn(
                "BROKER_POSITIONS_UNAVAILABLE",
                "",
                f"positions read failed: {type(error).__name__}: {error}",
                now,
            )

        try:
            self._all_orders = list(self._gateway.orders(None))
            self._orders_known = True
        except Exception as error:
            self._all_orders = []
            self._orders_known = False
            self._journal.warn(
                "BROKER_ORDERS_UNAVAILABLE",
                "",
                f"orders read failed: {type(error).__name__}: {error}",
                now,
            )

        magic = self._config.execution.magic
        self._own_positions_cache = [
            position for position in self._all_positions if position.magic == magic
        ]
        self._own_orders_cache = [
            order for order in self._all_orders if order.magic == magic
        ]

    # ------------------------------------------------------------------- pass
    def run_pass(self, now: int) -> EngineSnapshot:
        """One complete scan pass over a slice of the symbol list."""
        import time as _time

        started = _time.perf_counter()
        self._passes += 1
        self._arming.sweep(now)
        self._ensure_run(now)

        account = self._safe_account()
        equity = account.equity if account else 0.0
        may_trade, guard_codes = self._account_guard.check(equity, now)
        self._refresh_broker_state(now)
        if not self._positions_known:
            guard_codes.append("BROKER_POSITIONS_UNAVAILABLE")
        if not self._orders_known:
            guard_codes.append("BROKER_ORDERS_UNAVAILABLE")
        may_trade = may_trade and self._positions_known and self._orders_known
        if self._repo is not None:
            self._repo.save_risk_state(self._account_guard.state)

        resolved_symbols = [v for v in self._views.values() if v.resolved]
        slice_size = max(1, self._config.scan.symbols_per_slice)
        if resolved_symbols:
            for offset in range(min(slice_size, len(resolved_symbols))):
                index = (self._cursor + offset) % len(resolved_symbols)
                self._scan_symbol(resolved_symbols[index], account, now)
            self._cursor = (self._cursor + slice_size) % len(resolved_symbols)

        if self._execution.has_unresolved():
            truth = self._execution.reconcile(self._gateway, now)
            if truth is not None and truth.resolved:
                self._apply_broker_truth(truth, now)

        positions = list(self._own_positions_cache)
        orders = list(self._own_orders_cache)
        exposure = self._risk.exposure(
            "", positions, self._specs, equity if equity > 0 else 1.0
        )

        intent = self._arming.current
        current = self._execution.current
        # ``None`` rather than a default of False: an account nobody could read
        # must render as "unknown", never as "not demo", which would paint a
        # critical mismatch banner over a merely unreachable terminal.
        severity, account_code = account_verdict(
            self._environment, account.is_demo if account is not None else None
        )
        snapshot = EngineSnapshot(
            now=now,
            connected=self._safe_connected(),
            runtime=self._runtime,
            account=account,
            mode=self._mode,
            symbols=list(self._views.values()),
            exposure_open_pct=exposure.open_risk_pct,
            guard_codes=guard_codes,
            may_trade=may_trade,
            execution_state=current.state.name,
            execution_message=current.message,
            requires_manual_review=self._execution.requires_manual_review(),
            armed_symbol=intent.symbol if intent.armed else "",
            armed_seconds=self._arming.seconds_remaining(now),
            news_blind=self._calendar.is_news_blind,
            passes=self._passes,
            last_pass_ms=(_time.perf_counter() - started) * 1000.0,
            environment=self._environment,
            account_severity=severity,
            account_code=account_code,
            send_lock=send_refusal(self._environment, self._mode),
            positions_known=self._positions_known,
            orders_known=self._orders_known,
            positions=positions,
            working_orders=orders,
            exposure=exposure,
            guard_state=self._account_guard.state,
            execution=current,
            execution_unresolved=self._execution.has_unresolved(),
            journal_entries=self._journal.entries(),
            order_errors=self._errors_snapshot(),
            outcome_summary=(
                self._repo.outcome_summary() if self._repo is not None else {}
            ),
            persistence_ready=self._repo is not None and self._repo.ready,
        )
        # Ranking reads evidence, so it is part of the worker-produced read
        # model too. Importing lazily avoids an engine/scanner module cycle.
        from .scanner import build as build_opportunities

        snapshot.opportunities = build_opportunities(snapshot, self._config, self._repo)

        # SymbolView, Journal and execution records are mutable engine state.
        # A shallow list copy still lets the next worker pass mutate objects the
        # GUI is currently painting. Deep copy is the actual thread boundary.
        import copy

        return copy.deepcopy(snapshot)

    def _errors_snapshot(self) -> ErrorTally:
        import copy

        return copy.deepcopy(self._execution.errors)

    def _safe_connected(self) -> bool:
        try:
            return self._gateway.is_connected()
        except Exception:
            return False

    def _scan_symbol(self, view: SymbolView, account: AccountInfo | None, now: int) -> None:
        symbol = view.symbol
        spec = self._specs.get(symbol)
        if spec is None:
            view.last_error = "NO_SPEC"
            return

        tick = self._gateway.tick(symbol)
        snapshot = SymbolSnapshot(
            requested_symbol=view.requested,
            symbol=symbol,
            point=spec.point,
            digits=spec.digits,
        )

        if tick is None:
            snapshot.spread_state = SpreadState.NO_TICK
            snapshot.data_state = DataState.ERROR
            view.snapshot = snapshot
            return

        snapshot.bid = tick.bid
        snapshot.ask = tick.ask
        snapshot.tick_time = tick.time

        age = now - tick.time
        if age > self._config.scan.max_tick_age_seconds:
            snapshot.spread_state = SpreadState.STALE
            snapshot.data_state = DataState.STALE
            view.snapshot = snapshot
            return

        spread_points = (tick.ask - tick.bid) / spec.point if spec.point > 0 else 0.0
        snapshot.spread_points = spread_points
        tracker = self._spread.setdefault(symbol, SpreadTracker(self._config.scan))
        tracker.add(spread_points)
        state, ratio, percentile = tracker.classify(spread_points)
        snapshot.spread_state = state
        snapshot.spread_ratio = ratio
        snapshot.spread_percentile = percentile
        snapshot.data_state = DataState.READY
        view.snapshot = snapshot

        # ---- structure, only on a new closed bar -----------------------------
        m5_bars = self._gateway.bars(symbol, Timeframe.M5, self._config.scan.minimum_bars)
        if len(m5_bars) < 2:
            view.last_error = "INSUFFICIENT_HISTORY"
            return

        latest_closed = m5_bars[-2].time
        if self._last_bar_time.get(symbol) != latest_closed or symbol not in self._contexts:
            self._last_bar_time[symbol] = latest_closed
            bars_by_tf = {
                timeframe: self._gateway.bars(
                    symbol, timeframe, self._required_bars(timeframe)
                )
                for timeframe in ANALYSED_TIMEFRAMES
            }
            context = self._signals.build_context(symbol, bars_by_tf, snapshot, now=now)
            self._contexts[symbol] = context
            view.structure_built_at = now if context.valid else 0
            if not context.valid:
                view.last_error = "STRUCTURE_UNAVAILABLE"

        context = self._contexts.get(symbol)
        if context is None or not context.valid:
            view.signal = None
            view.plan = None
            view.bars = []
            view.zones = []
            return

        view.last_error = ""
        # A bounded slice: the chart shows about 120 candles and copying the
        # whole 300-bar window every pass would be wasted work on the hot path.
        view.bars = m5_bars[-140:]
        view.zones = context.zones
        view.regime_reason = context.regime.reason

        # ---- live evaluation --------------------------------------------------
        signal = self._signals.evaluate(context, snapshot, now)
        self._statistics.enrich(signal)
        if spec.fingerprint:
            signal.broker_spec_hash = spec.fingerprint
        # The pure signal engine creates a structural id before it knows the
        # contract. Evidence identity additionally includes parameter and broker
        # fingerprints, so a changed experiment can never inherit an older
        # signal's terminal state or outcome.
        signal.signal_id = evidence_signal_id(signal, signal.broker_spec_hash)
        view.signal = signal

        verdict = self._calendar.evaluate(symbol, self._runtime, now)
        view.news = verdict
        view.news_blocks = self._calendar.blocks_trading(verdict)

        stored_state = None
        if self._repo is not None and signal.direction != Direction.NONE:
            if not self._repo.signal_exists(signal.signal_id):
                self._repo.save_signal(signal, self._run_id)
                self._repo.save_features(
                    signal.signal_id, extract_features(context, signal, snapshot)
                )
            stored_state = self._repo.signal_state(signal.signal_id)

        # ---- planning ---------------------------------------------------------
        view.plan = None
        # One structural signal gets one execution lifecycle. A terminal signal
        # may not be previewed and submitted again: outcomes are intentionally
        # one-per-signal, so a retry would either overwrite evidence or create
        # a second execution whose result could never be persisted honestly.
        if stored_state == SignalState.ACTIVE or (
            stored_state is not None and is_terminal(stored_state)
        ):
            signal.state = stored_state
            return
        if signal.direction == Direction.NONE or signal.hard_blocked:
            return
        if view.news_blocks:
            signal.validation_codes.append(
                f"NEWS_{verdict.state.name}"
                if verdict.state != NewsState.CLEAR
                else "NEWS_BLOCKED"
            )
            return
        if account is None:
            return
        if not self._positions_known or not self._orders_known:
            signal.validation_codes.extend(
                code
                for known, code in (
                    (self._positions_known, "BROKER_POSITIONS_UNAVAILABLE"),
                    (self._orders_known, "BROKER_ORDERS_UNAVAILABLE"),
                )
                if not known and code not in signal.validation_codes
            )
            return
        # Use the unfiltered account view. On a netting account, foreign
        # same-symbol exposure would merge with this execution and make later
        # outcome attribution impossible without guessing.
        if self._guards.has_exposure(symbol, self._all_positions, self._all_orders):
            signal.validation_codes.append("ALREADY_EXPOSED")
            return

        plan = self._risk.build(
            signal,
            gateway=self._gateway,
            account=account,
            spec=spec,
            own_positions=self._own_positions_cache,
            specs=self._specs,
            now=now,
        )
        view.plan = plan

        if plan.valid:
            if self._repo is not None:
                self._repo.save_plan(plan)
                stored = self._repo.signal_state(signal.signal_id)
                if stored in (SignalState.CONFIRMED, None):
                    self._repo.update_signal_state(signal.signal_id, SignalState.PREVIEWED)
            signal.state = SignalState.PREVIEWED

    def _required_bars(self, timeframe: Timeframe) -> int:
        """Enough history for the slow EMA, ADX warm-up and the ATR median."""
        needed = max(
            self._config.scan.minimum_bars,
            self._config.structure.zone_lookback_bars + 20,
            260,
        )
        return needed

    # -------------------------------------------------------------- execution
    def arm(self, symbol: str, now: int) -> tuple[bool, str]:
        if self._execution.has_unresolved():
            return False, "EXECUTION_ALREADY_UNRESOLVED"
        if not self._positions_known or not self._orders_known:
            return False, "BROKER_STATE_UNAVAILABLE"
        view = next((v for v in self._views.values() if v.symbol == symbol), None)
        if view is None or view.plan is None or not view.plan.valid:
            return False, "NO_VALID_PLAN"
        if self._repo is not None:
            stored = self._repo.signal_state(view.plan.signal_id)
            if stored is not None and is_terminal(stored):
                return False, "SIGNAL_ALREADY_TERMINAL"
        if self._mode not in (RunMode.SHADOW, RunMode.DEMO_CONFIRM):
            return False, "ARMING_REQUIRES_CONFIRMABLE_MODE"
        if not self._arming.arm(view.plan, now):
            return False, "ARM_REFUSED"
        return True, ""

    def confirm(self, symbol: str, now: int) -> tuple[bool, str]:
        """Consume the armed intent and submit. The only path to an order."""
        view = next((v for v in self._views.values() if v.symbol == symbol), None)
        if view is None or view.plan is None or not view.plan.valid:
            self._arming.disarm("CURRENT_PLAN_UNAVAILABLE", now)
            return False, "NO_VALID_PLAN"

        if self._repo is not None:
            stored = self._repo.signal_state(view.plan.signal_id)
            if stored is not None and is_terminal(stored):
                self._arming.disarm("SIGNAL_ALREADY_TERMINAL", now)
                return False, "SIGNAL_ALREADY_TERMINAL"

        confirmed, reason = self._arming.confirm(view.plan, now)
        if not confirmed:
            return False, reason

        # Calendar is queried again at the last responsible moment. The pass
        # that produced the plan already checked it, but an external CSV may be
        # updated between paint and Confirm; a stale CLEAR is not a clearance.
        news = self._calendar.evaluate(symbol, self._runtime, now)
        if self._calendar.blocks_trading(news):
            return False, f"NEWS_{news.state.name}"

        account = self._safe_account()
        may_trade, codes = self._account_guard.check(
            account.equity if account is not None else 0.0, now
        )
        if not may_trade:
            return False, ";".join(codes)

        spec = self._specs.get(symbol)
        accepted, submit_reason = self._execution.submit(
            view.plan, self._mode, gateway=self._gateway, account=account, spec=spec, now=now
        )
        if accepted and view.signal is not None and not self._execution.current.terminal:
            self._account_guard.register_risk_used(view.plan.risk_percent, now)
        # A broker rejection/cancellation is already terminal and factual. It
        # produces a non-scorable NOT_FILLED outcome immediately; a successful
        # send waits for reconciliation to verify the actual fill first.
        if self._execution.current.terminal:
            if submit_reason == "SHADOW_MODE":
                self._apply_shadow_outcome(now)
            else:
                self._apply_broker_truth(
                    BrokerTruth(
                        resolved=True,
                        state=self._execution.current.state,
                        terminal=True,
                        source="SEND_RESULT",
                        detail=self._execution.current.message,
                    ),
                    now,
                )
        return accepted, submit_reason

    def _apply_shadow_outcome(self, now: int) -> None:
        """Persist a rehearsal as rehearsal, never as broker evidence."""
        record = self._execution.current
        if self._repo is None or not record.signal_id:
            return
        if self._repo.outcome_for_execution(record.execution_id) is not None:
            return
        outcome = Outcome(
            signal_id=record.signal_id,
            execution_id=record.execution_id,
            result="SHADOW",
            realized_r=0.0,
            mfe_r=None,
            mae_r=None,
            closed_at=record.created_at or now,
            source="SHADOW",
            evidence_quality="PREFLIGHT_ONLY",
            valid_for_statistics=False,
            **self._repo.signal_metadata(record.signal_id),
        )
        self._repo.save_outcome_with_state(outcome, SignalState.NOT_FILLED)

    def _apply_broker_truth(self, truth: BrokerTruth, now: int) -> None:
        """Advance lifecycle and persist one outcome from exact broker truth."""
        record = self._execution.current
        if self._repo is None or not record.signal_id:
            return

        if truth.state in (
            ExecState.PARTIALLY_FILLED,
            ExecState.FILLED,
            ExecState.POSITION_ACTIVE,
        ):
            self._repo.update_signal_state(record.signal_id, SignalState.ACTIVE)
            return
        if not truth.terminal:
            return
        if self._repo.outcome_for_execution(record.execution_id) is not None:
            return

        metadata = self._repo.signal_metadata(record.signal_id)
        if truth.state in (ExecState.CANCELLED, ExecState.REJECTED):
            result = "NOT_FILLED"
            signal_state = SignalState.NOT_FILLED
            valid = False
        else:
            reason = truth.close_reason.upper()
            if reason == "TP":
                result, signal_state = "TP", SignalState.TP
            elif reason == "SL":
                result, signal_state = "SL", SignalState.SL
            else:
                result, signal_state = "CLOSED", SignalState.CLOSED
            valid = result in ("TP", "SL")

        # A process can miss the visible ACTIVE phase while exact broker deals
        # prove that the position both opened and closed. Persist the implied
        # factual transition before the terminal one so lifecycle validation
        # remains strict without losing crash-recovered truth.
        if truth.state == ExecState.COMPLETED:
            self._repo.update_signal_state(record.signal_id, SignalState.ACTIVE)

        filled = truth.filled_volume or record.filled_volume
        risk_amount = 0.0
        if record.requested_volume > 0.0 and filled > 0.0:
            risk_amount = record.initial_risk_amount * min(
                1.0, filled / record.requested_volume
            )
        exact_prices = truth.entry_price > 0.0 and truth.exit_price > 0.0
        broker_close_time_known = not truth.deals or truth.closed_at > 0
        valid = (
            valid
            and risk_amount > 0.0
            and exact_prices
            and filled > 0.0
            and broker_close_time_known
        )
        realized_r = truth.net_profit / risk_amount if risk_amount > 0.0 else 0.0

        outcome = Outcome(
            signal_id=record.signal_id,
            execution_id=record.execution_id,
            result=result,
            realized_r=realized_r,
            mfe_r=None,
            mae_r=None,
            # A deal-backed outcome uses only the broker timestamp. Falling
            # back to reconciliation time would invent when the trade closed.
            # A send disposition has no deal and happened when its intent was
            # created, which is persisted even across restart recovery.
            closed_at=(
                truth.closed_at
                if truth.deals
                else (record.created_at or now)
            ),
            source="LIVE_DEMO",
            evidence_quality="BROKER_DEALS" if truth.deals else "BROKER_DISPOSITION",
            entry_price=truth.entry_price,
            exit_price=truth.exit_price,
            filled_volume=filled,
            net_profit=truth.net_profit,
            valid_for_statistics=valid,
            **metadata,
        )
        guard_after = None
        if truth.state == ExecState.COMPLETED:
            # Outcome, lifecycle and the loss-streak state are one durability
            # fact. Build the next guard state on a copy, commit it in the same
            # SQLite transaction, then publish it in memory only on success.
            import copy

            guard_after = copy.deepcopy(self._account_guard)
            guard_after.register_closed_profit(truth.net_profit, now)
        if self._repo.save_outcome_with_state(
            outcome,
            signal_state,
            risk_state=guard_after.state if guard_after is not None else None,
        ):
            if guard_after is not None:
                self._account_guard = guard_after

    def shutdown(self, now: int) -> None:
        """Finish provenance while still on the gateway/database owner thread."""
        if self._repo is not None and self._run_id:
            self._repo.finish_run(self._run_id, now)

    def acknowledge_unresolved(self, note: str, now: int) -> bool:
        return self._execution.acknowledge_unresolved(note, now)
