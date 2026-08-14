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
    NewsState,
    RunMode,
    SignalState,
    SpreadState,
    Timeframe,
)
from ..core.environment import Environment, account_verdict, capabilities, send_refusal
from ..core.execution import ExecutionEngine
from ..core.features import extract as extract_features
from ..core.guards import AccountRiskGuard, TradeGuards
from ..core.journal import Journal
from ..core.models import (
    AccountInfo,
    Bar,
    NewsVerdict,
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
from ..core.signals import SignalEngine, StructuralContext
from ..core.spread import SpreadTracker
from ..core.statistics import Statistics

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
        self._execution = ExecutionEngine(
            self._config, self._journal, environment=self._environment
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

        if self._repo is not None:
            self._execution.set_persistence(self._repo.save_execution)

    # ------------------------------------------------------------ properties
    @property
    def mode(self) -> RunMode:
        return self._mode

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

    # Public read accessors for the UI. The window used to reach into private
    # attributes for these, which quietly made every internal rename a UI break
    # and blurred the rule that the UI only ever reads what the engine offers.
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

    def own_positions(self):
        return self._own_positions()

    def working_orders(self):
        return self._safe_orders()

    def exposure_summary(self, account=None):
        equity = account.equity if account and account.equity > 0 else 1.0
        return self._risk.exposure("", self._own_positions(), self._specs, equity)

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
            if not account.is_demo:
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
        if self._execution.requires_manual_review():
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
        self._account_guard = AccountRiskGuard(self._config.risk)
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
        equity = account.equity if account else 0.0
        stored = self._repo.load_risk_state() if self._repo is not None else None
        self._account_guard.initialize(equity, now, stored)

        if self._repo is not None:
            self._execution.recover_after_restart(self._repo.load_unresolved_execution(), now)
            self._journal.extend(self._repo.recent_events(100))

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

    # ------------------------------------------------------------------- pass
    def run_pass(self, now: int) -> EngineSnapshot:
        """One complete scan pass over a slice of the symbol list."""
        import time as _time

        started = _time.perf_counter()
        self._passes += 1
        self._arming.sweep(now)

        account = self._safe_account()
        equity = account.equity if account else 0.0
        may_trade, guard_codes = self._account_guard.check(equity, now)
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
            self._execution.reconcile(self._gateway, now)

        exposure = self._risk.exposure(
            "", self._own_positions(), self._specs, equity if equity > 0 else 1.0
        )

        intent = self._arming.current
        current = self._execution.current
        # ``None`` rather than a default of False: an account nobody could read
        # must render as "unknown", never as "not demo", which would paint a
        # critical mismatch banner over a merely unreachable terminal.
        severity, account_code = account_verdict(
            self._environment, account.is_demo if account is not None else None
        )
        return EngineSnapshot(
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
        )

    def _safe_connected(self) -> bool:
        try:
            return self._gateway.is_connected()
        except Exception:
            return False

    def _own_positions(self):
        try:
            return self._gateway.positions(self._config.execution.magic)
        except Exception:
            return []

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
        view.signal = signal

        verdict = self._calendar.evaluate(symbol, self._runtime, now)
        view.news = verdict
        view.news_blocks = self._calendar.blocks_trading(verdict)

        if self._repo is not None and signal.direction != Direction.NONE:
            if not self._repo.signal_exists(signal.signal_id):
                self._repo.save_signal(signal, self._run_id)
                self._repo.save_features(
                    signal.signal_id, extract_features(context, signal, snapshot)
                )

        # ---- planning ---------------------------------------------------------
        view.plan = None
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
        if self._guards.has_exposure(symbol, self._own_positions(), self._safe_orders()):
            signal.validation_codes.append("ALREADY_EXPOSED")
            return

        plan = self._risk.build(
            signal,
            gateway=self._gateway,
            account=account,
            spec=spec,
            own_positions=self._own_positions(),
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

    def _safe_orders(self):
        try:
            return self._gateway.orders(self._config.execution.magic)
        except Exception:
            return []

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
        view = next((v for v in self._views.values() if v.symbol == symbol), None)
        if view is None or view.plan is None or not view.plan.valid:
            return False, "NO_VALID_PLAN"
        if self._mode != RunMode.DEMO_CONFIRM:
            return False, "ARMING_REQUIRES_DEMO_CONFIRM_MODE"
        if not self._arming.arm(view.plan, now):
            return False, "ARM_REFUSED"
        return True, ""

    def confirm(self, symbol: str, now: int) -> tuple[bool, str]:
        """Consume the armed intent and submit. The only path to an order."""
        view = next((v for v in self._views.values() if v.symbol == symbol), None)
        if view is None or view.plan is None or not view.plan.valid:
            return False, "NO_VALID_PLAN"

        confirmed, reason = self._arming.confirm(view.plan, now)
        if not confirmed:
            return False, reason

        may_trade, codes = self._account_guard.check(
            self._safe_account().equity if self._safe_account() else 0.0, now
        )
        if not may_trade:
            return False, ";".join(codes)

        account = self._safe_account()
        spec = self._specs.get(symbol)
        accepted, submit_reason = self._execution.submit(
            view.plan, self._mode, gateway=self._gateway, account=account, spec=spec, now=now
        )
        if accepted and view.signal is not None:
            self._account_guard.register_risk_used(view.plan.risk_percent, now)
            self._outcomes.open(view.signal, view.plan.entry, now)
            if self._repo is not None:
                self._repo.update_signal_state(view.signal.signal_id, SignalState.ACTIVE)
        return accepted, submit_reason

    def acknowledge_unresolved(self, note: str, now: int) -> bool:
        return self._execution.acknowledge_unresolved(note, now)
