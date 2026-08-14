"""The single boundary where an order leaves this application.

This is the ONLY module permitted to call ``BrokerGateway.send_order``. The test
suite asserts that no other module in the package even references it, so no
future change can quietly open a second path that skips the guards.

Real accounts are blocked unconditionally. There is no configuration, no input
and no enum member that reaches a live account — the check is a hard return, not
a policy flag. The MT5 adapter refuses again on its own, sharing no code with
this check, so editing one away does not disable the other.

Reconciliation is built on MetaQuotes' documented reality that trade transaction
delivery is UNORDERED, may repeat, and can be dropped when the terminal's
1024-element queue overflows. The desktop build has a fourth hazard the EA did
not: the IPC connection to the terminal can simply drop mid-flight. Nothing here
waits for a particular event sequence — every pass re-reads authoritative state,
deals are recorded by ticket so a replay cannot double-count, and anything left
unresolved past a grace period escalates rather than resolves.

**The governing rule:** ``terminal`` means RESOLVED. It never means "gave up".
An earlier version of the MQL5 engine marked a genuinely unresolved execution
terminal after the grace period so the engine would not wedge — which released
the submit gate and allowed the next order out in precisely the situation where
nobody knew whether the previous one was live. That is exactly backwards: "we do
not know" is the strongest possible reason to send nothing further.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import AppConfig
from .enums import ExecState, RunMode
from .environment import Environment, capabilities
from .hashing import fnv1a64
from .order_errors import ErrorTally
from .journal import Journal
from .models import (
    DEAL_ENTRY_OUT,
    DEAL_ENTRY_OUT_BY,
    AccountInfo,
    ExecutionRecord,
    SymbolSpec,
    TradePlan,
)
from .ports import BrokerGateway
from .preflight import Preflight

# MetaTrader retcodes the engine interprets. Listed rather than imported so the
# core stays free of the MT5 package.
RETCODE_DONE = 10009
RETCODE_DONE_PARTIAL = 10010
RETCODE_PLACED = 10008


def may_be_auto_terminal(state: ExecState) -> bool:
    """May reconciliation record this state as finished?

    ``ExecState.UNKNOWN`` is deliberately absent. It means "not resolved", and a
    state meaning not-resolved must never be auto-recorded as finished — doing
    so was the P0 this predicate exists to prevent.

    The single documented exception is ``acknowledge_unresolved()``, where a
    human has inspected the account and taken responsibility for the decision.
    """
    return state in (ExecState.COMPLETED, ExecState.REJECTED, ExecState.CANCELLED)


@dataclass
class BrokerTruth:
    """What the broker says happened, rebuilt from live and historical state
    rather than from events that may never have arrived."""

    resolved: bool = False
    state: ExecState = ExecState.UNKNOWN
    terminal: bool = False
    source: str = ""
    detail: str = ""
    filled_volume: float = 0.0
    position_id: int = 0


class DealLedger:
    """Admission gate for deal tickets — not a log.

    MetaQuotes documents that transaction delivery may repeat, so a deal ticket
    is allowed to move execution state **at most once**. Recording the ticket
    and then mutating state regardless makes the idempotency decorative: a
    replayed fill double-counts and can drive a partially-filled order to FILLED
    on volume that only ever arrived once.

    The in-memory set is a fast path. The durable answer lives in the
    ``deals`` table, which is why ``admit`` takes an optional persistent
    delegate — after a restart, memory is empty but the ticket is still spent.
    """

    def __init__(self, persistent_admit=None) -> None:
        self._seen: set[int] = set()
        self._persistent_admit = persistent_admit

    def admit(self, deal_ticket: int, **row) -> bool:
        """True the first time this ticket is seen, False on every replay."""
        if deal_ticket <= 0:
            return False
        if deal_ticket in self._seen:
            return False
        if self._persistent_admit is not None:
            if not self._persistent_admit(deal_ticket, **row):
                self._seen.add(deal_ticket)
                return False
        self._seen.add(deal_ticket)
        return True

    def load(self, tickets) -> None:
        self._seen.update(tickets)


class ExecutionEngine:
    def __init__(
        self,
        config: AppConfig | None = None,
        journal: Journal | None = None,
        ledger: DealLedger | None = None,
        environment: str = Environment.DEMO,
    ) -> None:
        self._config = config or AppConfig()
        self._journal = journal or Journal()
        self._ledger = ledger or DealLedger()
        self._preflight = Preflight(self._config)
        self._magic = self._config.execution.magic
        self._current = ExecutionRecord(state=ExecState.IDLE)
        self._save = None
        # The retcode tally lives here because this is where retcodes arrive.
        # It used to live on the window, fed by nothing, so the whole taxonomy
        # was dead code and every diagnostics bundle reported zero order errors
        # no matter how many the broker had refused.
        self._errors = ErrorTally()
        # Defaults to DEMO because that is what this build has always been: the
        # one environment where a send is reachable at all. Declaring it makes
        # the other two express their refusal structurally rather than by
        # happening not to be configured for trading.
        self._environment = Environment.parse(environment)

    @property
    def environment(self) -> str:
        return self._environment

    @property
    def errors(self) -> ErrorTally:
        """Order rejections this session, grouped by what they were.

        A single rejection is noise; a pattern is a diagnosis. Forty
        INVALID_STOPS against one symbol says its stops level changed, and no
        per-order message ever says that.
        """
        return self._errors

    def set_environment(self, environment: str) -> str:
        """Re-declare the environment. Returns the value actually adopted.

        There is no path here that can make a locked environment sendable —
        :func:`send_refusal` recomputes the lock from the name on every submit,
        so this setter cannot leave a stale permission behind.
        """
        self._environment = Environment.parse(environment)
        return self._environment

    def set_persistence(self, save_callable) -> None:
        """Attach the repository writer. Optional: an offline session persists
        nothing and still executes correctly."""
        self._save = save_callable

    @property
    def current(self) -> ExecutionRecord:
        return self._current

    # ------------------------------------------------------------------ state
    def has_unresolved(self) -> bool:
        return (
            self._current.execution_id != ""
            and not self._current.terminal
            and self._current.state != ExecState.IDLE
        )

    def requires_manual_review(self) -> bool:
        """True when the engine is refusing to submit because an execution could
        not be resolved. Distinct from merely having one in flight."""
        return (
            self._current.execution_id != ""
            and not self._current.terminal
            and self._current.state == ExecState.UNKNOWN
        )

    def _persist(self, now: int) -> None:
        self._current.updated_at = now
        if self._save is not None:
            self._save(self._current)

    def recover_after_restart(self, record: ExecutionRecord | None, now: int) -> None:
        """Restore an in-flight execution so reconciliation resumes instead of
        the order being forgotten.

        Because unresolved records are stored with ``terminal = 0``, a block
        raised before a crash is still a block after the restart.
        """
        if record is None or record.execution_id == "":
            return
        self._current = record
        if record.state != ExecState.UNKNOWN:
            self._current.state = ExecState.RECONCILING
        self._journal.warn(
            "EXECUTION_RECOVERED",
            record.symbol,
            f"execution {record.execution_id} was in flight at shutdown; reconciling",
            now,
        )
        self._persist(now)

    # ----------------------------------------------------------------- submit
    def submit(
        self,
        plan: TradePlan,
        mode: RunMode,
        *,
        gateway: BrokerGateway,
        account: AccountInfo | None,
        spec: SymbolSpec | None,
        now: int,
    ) -> tuple[bool, str]:
        """Submit a plan. Returns ``(accepted, reason)``.

        ``mode`` decides whether an order actually leaves:

        * ``ALERT_ONLY`` — never sends.
        * ``SHADOW`` — runs the full preflight and records the intent, sends
          nothing. Identical validation and persistence path, so a shadow run
          exercises the real code rather than a simulation of it.
        * ``DEMO_CONFIRM`` — sends, demo accounts only, and only after the
          caller has already consumed an armed intent.
        """
        # The declared environment is consulted before anything else, because
        # it is the one refusal that does not depend on the broker telling the
        # truth. Every other check below reads something the terminal reported
        # — the account's demo flag, the symbol's specification — and a session
        # whose terminal was switched underneath it can be lied to. This one
        # reads only what the operator declared.
        caps = capabilities(self._environment)
        if not caps.may_use(mode):
            return False, f"MODE_NOT_AVAILABLE_IN_{caps.environment}"

        if mode == RunMode.ALERT_ONLY:
            return False, "ALERT_ONLY_MODE"

        # Unconditional. Not a setting, not overridable.
        if account is None:
            return False, "NO_ACCOUNT"
        if not account.is_demo:
            self._journal.error(
                "REAL_ACCOUNT_BLOCKED",
                plan.symbol,
                "execution refused: this build never trades a live account",
                now,
            )
            return False, "REAL_ACCOUNT_BLOCKED"

        # One in-flight execution at a time. Concurrent sends cannot be
        # attributed reliably under unordered transaction delivery.
        if self.has_unresolved():
            if self.requires_manual_review():
                return False, "UNRESOLVED_MANUAL_REVIEW_REQUIRED"
            return False, "EXECUTION_ALREADY_UNRESOLVED"

        result = self._preflight.validate(
            plan, gateway=gateway, account=account, spec=spec, now=now
        )
        if not result.ok or result.request is None:
            return False, result.reason

        self._current = ExecutionRecord(
            execution_id=fnv1a64(f"{plan.plan_id}|{now}"),
            plan_id=plan.plan_id,
            signal_id=plan.signal_id,
            symbol=plan.symbol,
            requested_volume=plan.lot_size,
            created_at=now,
            state=ExecState.SUBMITTING,
            terminal=False,
        )

        if mode == RunMode.SHADOW:
            self._current.state = ExecState.COMPLETED
            self._current.terminal = True
            self._current.message = "SHADOW_NOT_SENT"
            self._persist(now)
            self._journal.info(
                "SHADOW_EXECUTION",
                plan.symbol,
                f"plan {plan.plan_id} passed preflight; not sent (shadow mode)",
                now,
            )
            return True, "SHADOW_MODE"

        # The last gate before the only line in this application that can move
        # money. Recomputed from the environment name here rather than reusing
        # the `caps` read at the top of the method: between the two the plan
        # went through preflight, which touches the gateway, and a check whose
        # answer was cached before that is a check of a stale world. It costs a
        # dataclass construction and it is the cheapest thing on this path.
        lock = capabilities(self._environment).send_lock
        if lock:
            self._current.state = ExecState.CANCELLED
            self._current.terminal = True
            self._current.message = lock
            self._persist(now)
            self._journal.error(
                lock,
                plan.symbol,
                f"execution refused: environment {self._environment} cannot send orders",
                now,
            )
            return False, lock

        # Persist the intent BEFORE sending. If the app dies between here and
        # the reply, restart recovery still finds the record.
        self._persist(now)

        outcome = gateway.send_order(result.request)

        self._current.request_id = outcome.request_id
        self._current.order_ticket = outcome.order
        self._current.deal_ticket = outcome.deal
        self._current.retcode = outcome.retcode
        self._current.message = outcome.comment

        if not outcome.ok:
            # Classify before deciding what to say. The retcode alone is not a
            # diagnosis, and the three categories want three different
            # responses: a REQUEST error is this application's own defect, a
            # MARKET error is the market, an ACCOUNT error is the operator's.
            error = self._errors.record(outcome.retcode, plan.symbol, now)
            self._current.state = ExecState.REJECTED
            self._current.terminal = True
            if error.is_defect:
                # Never presented as something to retry. Sending the identical
                # malformed request again fails identically forever, and saying
                # so converts an infinite loop into one clear failure.
                self._journal.error(
                    "ORDER_REQUEST_DEFECT",
                    plan.symbol,
                    f"{error.code}: this build constructed an order the broker "
                    f"rejected as invalid — not retryable",
                    now,
                )
            reason = f"ORDER_SEND_FAILED({error.code}:{outcome.comment})"
        elif outcome.retcode == RETCODE_DONE:
            self._current.state = ExecState.FILLED
            reason = ""
        elif outcome.retcode == RETCODE_DONE_PARTIAL:
            self._current.state = ExecState.PARTIALLY_FILLED
            reason = ""
        elif outcome.retcode == RETCODE_PLACED:
            self._current.state = ExecState.ACCEPTED
            reason = ""
        else:
            # Anything else is genuinely unknown until reconciled. Treating an
            # unrecognised retcode as failure risks a live position nobody
            # tracks.
            self._current.state = ExecState.UNKNOWN
            reason = f"UNKNOWN_RETCODE({outcome.retcode}:{outcome.comment})"

        self._persist(now)
        return outcome.ok, reason

    # ------------------------------------------------------------ broker truth
    #
    # Four sources, consulted in descending order of authority. Each answers a
    # different question, and consulting only one is how a live order gets
    # mistaken for nothing having happened:
    #
    #   1. Open positions  — "is there a position right now"
    #   2. Working orders  — "is an order still live but unfilled"
    #   3. History orders  — "what was the order's final disposition"
    #   4. History deals   — "what actually executed"

    def _find_open_position(self, gateway: BrokerGateway) -> BrokerTruth | None:
        for position in gateway.positions(self._magic):
            matches_id = (
                self._current.position_id > 0
                and position.position_id == self._current.position_id
            )
            if not matches_id and position.symbol != self._current.symbol:
                continue
            return BrokerTruth(
                resolved=True,
                state=ExecState.POSITION_ACTIVE,
                terminal=False,  # a live position is not a finished execution
                source="POSITION",
                detail=f"position {position.position_id} open",
                filled_volume=position.volume,
                position_id=position.position_id,
            )
        return None

    def _find_working_order(self, gateway: BrokerGateway) -> BrokerTruth | None:
        for order in gateway.orders(self._magic):
            if self._current.order_ticket > 0:
                if order.ticket != self._current.order_ticket and order.symbol != self._current.symbol:
                    continue
            elif order.symbol != self._current.symbol:
                continue
            return BrokerTruth(
                resolved=True,
                state=ExecState.ACCEPTED,
                terminal=False,  # still working: emphatically not finished
                source="WORKING_ORDER",
                detail=f"order {order.ticket} still live",
            )
        return None

    def _resolve_history_order(
        self, gateway: BrokerGateway, since: int, until: int
    ) -> BrokerTruth | None:
        """Map a completed order's final state.

        Only reached when the order is no longer working, so every branch here
        is a definite disposition. A transitional state says nothing final and
        is reported as *no answer* rather than an invented one.
        """
        if self._current.order_ticket <= 0:
            return None
        for order in gateway.history_orders(since, until, self._magic):
            if order.ticket != self._current.order_ticket:
                continue
            state = order.state.upper()
            if state == "FILLED":
                return BrokerTruth(
                    resolved=True,
                    state=ExecState.FILLED,
                    terminal=False,  # filled, but the position's fate is open
                    source="HISTORY_ORDER",
                    detail=f"order {order.ticket} filled",
                    filled_volume=order.volume_initial,
                )
            if state == "PARTIAL":
                return BrokerTruth(
                    resolved=True,
                    state=ExecState.PARTIALLY_FILLED,
                    terminal=False,
                    source="HISTORY_ORDER",
                    detail=f"order {order.ticket} partially filled",
                )
            if state in ("CANCELED", "CANCELLED", "EXPIRED"):
                return BrokerTruth(
                    resolved=True,
                    state=ExecState.CANCELLED,
                    terminal=True,
                    source="HISTORY_ORDER",
                    detail=f"order {order.ticket} cancelled/expired",
                )
            if state == "REJECTED":
                return BrokerTruth(
                    resolved=True,
                    state=ExecState.REJECTED,
                    terminal=True,
                    source="HISTORY_ORDER",
                    detail=f"order {order.ticket} rejected",
                )
            return None
        return None

    def _resolve_from_deals(
        self, gateway: BrokerGateway, since: int, until: int
    ) -> BrokerTruth | None:
        """Sum this execution's deals.

        An IN followed by a matching OUT means the trade opened and closed while
        we were not watching — a genuinely finished execution, not a missing one.
        """
        volume_in = volume_out = 0.0
        position_id = 0
        matched = 0

        for deal in gateway.history_deals(since, until, self._magic):
            if deal.symbol != self._current.symbol:
                continue
            # Prefer an exact link when we have one; otherwise magic + symbol
            # within the window is the best available correlation.
            if (
                self._current.order_ticket > 0
                and deal.order != self._current.order_ticket
                and self._current.position_id > 0
                and deal.position_id != self._current.position_id
            ):
                continue

            if deal.entry == 0:  # IN
                volume_in += deal.volume
            elif deal.entry in (DEAL_ENTRY_OUT, DEAL_ENTRY_OUT_BY):
                volume_out += deal.volume
            if position_id == 0:
                position_id = deal.position_id
            matched += 1

        if matched == 0:
            return None

        truth = BrokerTruth(
            resolved=True,
            source="HISTORY_DEAL",
            filled_volume=volume_in,
            position_id=position_id,
        )
        if volume_in > 0.0 and volume_out + 1e-8 >= volume_in:
            truth.state = ExecState.COMPLETED
            truth.terminal = True
            truth.detail = f"opened {volume_in:.2f} and closed {volume_out:.2f}"
        else:
            truth.state = ExecState.FILLED
            truth.terminal = False
            truth.detail = f"filled {volume_in:.2f}, {volume_in - volume_out:.2f} still open"
        return truth

    def resolve_from_broker(self, gateway: BrokerGateway, now: int) -> BrokerTruth:
        """Consult all four sources. An unresolved truth means every one was
        silent — which is a finding, not an absence of one."""
        # The window is anchored on when this execution was created, widened so
        # a clock skew between app and server cannot hide the records.
        since = self._current.created_at - 3600 if self._current.created_at > 0 else now - 86400
        until = now + 3600

        for resolver in (
            lambda: self._find_open_position(gateway),
            lambda: self._find_working_order(gateway),
            lambda: self._resolve_history_order(gateway, since, until),
            lambda: self._resolve_from_deals(gateway, since, until),
        ):
            try:
                truth = resolver()
            except Exception as error:  # a gateway that raises is not an answer
                self._journal.warn(
                    "BROKER_TRUTH_SOURCE_FAILED",
                    self._current.symbol,
                    f"a reconciliation source raised: {error}",
                    now,
                )
                continue
            if truth is not None and truth.resolved:
                return truth

        return BrokerTruth(resolved=False)

    # ------------------------------------------------------------- reconcile
    def reconcile(self, gateway: BrokerGateway, now: int) -> None:
        """Rebuild the truth from the broker.

        Transaction events can be dropped entirely when the terminal's queue
        overflows, and the IPC link can drop outright, so nothing may depend on
        an event arriving.
        """
        if not self.has_unresolved():
            return

        truth = self.resolve_from_broker(gateway, now)

        if truth.resolved:
            self._current.state = truth.state
            # Belt and braces: even a resolver bug cannot mark a
            # not-actually-finished state as finished and reopen the gate.
            self._current.terminal = truth.terminal and may_be_auto_terminal(truth.state)
            self._current.message = truth.detail
            if truth.position_id > 0:
                self._current.position_id = truth.position_id
            if truth.filled_volume > 0.0:
                self._current.filled_volume = truth.filled_volume
            self._journal.info(
                "RECONCILED",
                self._current.symbol,
                f"execution {self._current.execution_id} resolved as "
                f"{truth.state.name} via {truth.source} ({truth.detail})",
                now,
            )
            self._persist(now)
            return

        # Not resolvable yet. Inside the grace period this is normal — the
        # server may simply not have answered.
        grace = self._config.execution.reconcile_grace_seconds
        if now - self._current.updated_at <= grace:
            self._current.state = ExecState.RECONCILING
            self._persist(now)
            return

        # Past the grace period with all four broker sources silent. This is a
        # real unknown: an order may be live that this app cannot see. The
        # execution stays NON-terminal, which keeps has_unresolved() true, which
        # keeps the submit gate shut — and because the record is stored with
        # terminal = 0, the block survives a restart as well.
        #
        # Only a deliberate operator acknowledgement clears it.
        if self._current.state != ExecState.UNKNOWN:
            self._journal.error(
                "RECONCILIATION_FAILED",
                self._current.symbol,
                f"execution {self._current.execution_id} unresolved after {grace}s across "
                "positions, working orders, history orders and history deals; "
                "submission is blocked until acknowledged",
                now,
            )

        self._current.state = ExecState.UNKNOWN
        self._current.terminal = False
        self._current.message = "UNRESOLVED_MANUAL_REVIEW_REQUIRED"
        self._persist(now)

    def acknowledge_unresolved(self, operator_note: str, now: int) -> bool:
        """Operator escape hatch.

        Without this the engine would wedge permanently on an unresolvable
        execution, and a permanently wedged system gets "fixed" by deleting the
        database — which loses the evidence too. Clearing is a deliberate,
        logged act that records who decided the account was verified.
        """
        if not self.requires_manual_review():
            return False
        if not operator_note.strip():
            return False

        self._current.terminal = True
        self._current.message = f"ACKNOWLEDGED: {operator_note}"
        self._journal.warn(
            "UNRESOLVED_ACKNOWLEDGED",
            self._current.symbol,
            f"execution {self._current.execution_id} cleared by operator: {operator_note}",
            now,
        )
        self._persist(now)
        return True

    # ------------------------------------------------------------------ deals
    def apply_deal(self, deal, now: int) -> bool:
        """Fold one deal into execution state, at most once.

        Returns True when the deal was admitted. A replayed ticket is refused
        here, before it can touch ``filled_volume`` — the defect that made the
        MQL5 ledger's idempotency decorative was recording the ticket and then
        mutating state regardless.
        """
        admitted = self._ledger.admit(
            deal.ticket,
            execution_id=self._current.execution_id,
            symbol=deal.symbol,
            entry=deal.entry,
            volume=deal.volume,
            price=deal.price,
            net_profit=deal.net_profit,
            recorded_at=now,
        )
        if not admitted:
            self._journal.debug(
                "DEAL_REPLAY_IGNORED", deal.symbol, f"deal {deal.ticket} already applied", now
            )
            return False

        if not self.has_unresolved():
            return True
        if deal.symbol != self._current.symbol:
            return True

        if deal.order > 0:
            self._current.order_ticket = deal.order
        if deal.position_id > 0:
            self._current.position_id = deal.position_id

        if deal.entry in (DEAL_ENTRY_OUT, DEAL_ENTRY_OUT_BY):
            self._current.state = ExecState.COMPLETED
            self._current.terminal = True
        else:
            self._current.filled_volume += deal.volume
            self._current.state = (
                ExecState.FILLED
                if self._current.filled_volume + 1e-8 >= self._current.requested_volume
                else ExecState.PARTIALLY_FILLED
            )
        self._persist(now)
        return True
