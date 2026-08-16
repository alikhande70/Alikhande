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

from dataclasses import dataclass, field

from ..config import AppConfig
from .enums import Direction, ExecState, RunMode
from .environment import Environment, capabilities
from .hashing import fnv1a64
from .order_errors import ErrorCategory, ErrorTally
from .journal import Journal
from .models import (
    DEAL_ENTRY_OUT,
    DEAL_ENTRY_OUT_BY,
    DEAL_ENTRY_INOUT,
    AccountInfo,
    DealInfo,
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
    closed_volume: float = 0.0
    order_ticket: int = 0
    position_id: int = 0
    deals: tuple[DealInfo, ...] = field(default_factory=tuple)
    entry_price: float = 0.0
    exit_price: float = 0.0
    net_profit: float = 0.0
    close_reason: str = ""
    closed_at: int = 0
    ambiguous: bool = False


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

    def recover_after_restart(
        self,
        record: ExecutionRecord | None,
        now: int,
        *,
        reconcile: bool = True,
    ) -> None:
        """Restore an in-flight execution so reconciliation resumes instead of
        the order being forgotten.

        Because unresolved records are stored with ``terminal = 0``, a block
        raised before a crash is still a block after the restart.
        """
        if record is None or record.execution_id == "":
            return
        self._current = record
        if reconcile and record.state != ExecState.UNKNOWN:
            self._current.state = ExecState.RECONCILING
        self._journal.warn(
            "EXECUTION_RECOVERED" if reconcile else "OUTCOME_COMMIT_RECOVERED",
            record.symbol,
            (
                f"execution {record.execution_id} was in flight at shutdown; reconciling"
                if reconcile
                else f"execution {record.execution_id} retained terminal disposition "
                f"{record.state.name}; committing its missing outcome"
            ),
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

        # A broker account is needed even for Shadow because the identical
        # permissions, sizing and OrderCheck path must run. Only a mode that can
        # actually send is restricted to demo here; Shadow returns before the
        # send boundary and is the supported rehearsal on a real account.
        if account is None:
            return False, "NO_ACCOUNT"
        if mode == RunMode.DEMO_CONFIRM and not account.is_demo:
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

        # A unique token is created before OrderCheck so the request checked is
        # byte-for-byte the request sent. It is persisted before the sole send
        # boundary, allowing recovery to find broker records even when the
        # process dies before receiving order/deal tickets.
        import uuid

        correlation_key = f"AK-{uuid.uuid4().hex[:16].upper()}"
        result = self._preflight.validate(
            plan,
            gateway=gateway,
            account=account,
            spec=spec,
            now=now,
            correlation_comment=correlation_key,
        )
        if not result.ok or result.request is None:
            return False, result.reason

        self._current = ExecutionRecord(
            execution_id=fnv1a64(f"{plan.plan_id}|{now}|{correlation_key}"),
            plan_id=plan.plan_id,
            signal_id=plan.signal_id,
            symbol=plan.symbol,
            mode=mode,
            requested_volume=plan.lot_size,
            correlation_key=correlation_key,
            direction=plan.direction,
            planned_entry=plan.entry,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            initial_risk_amount=(
                result.actual_risk_amount
                or plan.actual_risk_amount
                or plan.risk_amount
            ),
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

        # Defence immediately before the only send call as well as at the top
        # of the Demo path. A future refactor cannot turn Shadow's real-account
        # rehearsal permission into real-account execution by moving a return.
        if not account.is_demo:
            self._current.state = ExecState.CANCELLED
            self._current.terminal = True
            self._current.message = "REAL_ACCOUNT_BLOCKED"
            self._persist(now)
            return False, "REAL_ACCOUNT_BLOCKED"

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

        try:
            outcome = gateway.send_order(result.request)
        except Exception as error:
            # The transport may fail after the terminal accepted the request.
            # That is not a rejection and must never release the submit gate.
            # The pre-send record plus correlation key let reconciliation find
            # the broker truth without depending on a response ticket.
            self._current.state = ExecState.UNKNOWN
            self._current.terminal = False
            self._current.message = (
                f"ORDER_SEND_UNCERTAIN({type(error).__name__}: {error})"
            )
            self._journal.error(
                "ORDER_SEND_UNCERTAIN",
                plan.symbol,
                "order transport raised after durable intent; broker truth must be reconciled",
                now,
            )
            self._persist(now)
            return False, self._current.message

        self._current.request_id = outcome.request_id
        self._current.order_ticket = outcome.order
        self._current.deal_ticket = outcome.deal
        self._current.retcode = outcome.retcode
        self._current.message = outcome.comment

        error = self._errors.record(outcome.retcode, plan.symbol, now)
        if not outcome.definitive or error.category == ErrorCategory.UNKNOWN:
            # No reply, a transport-level uncertainty, or a broker code this
            # build does not understand cannot establish non-execution. Keep
            # the durable intent open and let exact broker state resolve it.
            self._current.state = ExecState.UNKNOWN
            self._current.terminal = False
            if not outcome.definitive:
                reason = f"ORDER_SEND_UNCERTAIN({error.code}:{outcome.comment})"
            else:
                reason = f"UNKNOWN_RETCODE({outcome.retcode}:{outcome.comment})"
        elif outcome.retcode == 10007:
            self._current.state = ExecState.CANCELLED
            self._current.terminal = True
            reason = f"ORDER_CANCELLED({outcome.comment})"
        elif not outcome.ok:
            # Classify before deciding what to say. The retcode alone is not a
            # diagnosis, and the three categories want three different
            # responses: a REQUEST error is this application's own defect, a
            # MARKET error is the market, an ACCOUNT error is the operator's.
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
        else:  # defensive: accepted flag with a non-accepted known code
            self._current.state = ExecState.UNKNOWN
            self._current.terminal = False
            reason = f"INCONSISTENT_ORDER_RESULT({outcome.retcode}:{outcome.comment})"

        self._persist(now)
        return outcome.ok, reason

    # ------------------------------------------------------------ broker truth
    # Identity is never inferred from symbol. A symbol is not a transaction
    # identifier: two scanner trades can share it, and a crash may leave us
    # without the response tickets. Every source must therefore match an exact
    # broker ticket/position id or the unique comment persisted before send.

    def _comment_matches(self, comment: str) -> bool:
        return bool(self._current.correlation_key) and comment == self._current.correlation_key

    def _deal_directly_matches_current(self, deal: DealInfo) -> bool:
        """A deal identity that does not rely on shared netting position id."""
        return bool(
            (self._current.deal_ticket > 0 and deal.ticket == self._current.deal_ticket)
            or (self._current.order_ticket > 0 and deal.order == self._current.order_ticket)
            or self._comment_matches(deal.comment)
        )

    @staticmethod
    def _ambiguous(
        source: str,
        detail: str,
        *,
        deals: tuple[DealInfo, ...] = (),
        order_ticket: int = 0,
        position_id: int = 0,
    ) -> BrokerTruth:
        return BrokerTruth(
            resolved=True,
            state=ExecState.UNKNOWN,
            terminal=False,
            source=source,
            detail=detail,
            ambiguous=True,
            deals=deals,
            order_ticket=order_ticket,
            position_id=position_id,
        )

    def _find_open_position(
        self, gateway: BrokerGateway, learned_position_id: int = 0
    ) -> BrokerTruth | None:
        matches = []
        # Do not pre-filter by magic. A broker/manual close can create related
        # rows with a different magic; exact position/comment identity below is
        # the attribution boundary and is stronger than an EA-wide tag.
        for position in gateway.positions(None):
            expected_position = self._current.position_id or learned_position_id
            exact = bool(
                (expected_position > 0 and position.position_id == expected_position)
                or self._comment_matches(position.comment)
            )
            if exact:
                matches.append(position)
        if len(matches) > 1:
            return self._ambiguous("POSITION", "multiple positions matched one execution")
        if not matches:
            return None
        position = matches[0]
        if position.symbol != self._current.symbol:
            return self._ambiguous(
                "POSITION", "exact position identity belongs to a different symbol"
            )
        return BrokerTruth(
            resolved=True,
            state=ExecState.POSITION_ACTIVE,
            terminal=False,
            source="POSITION",
            detail=f"position {position.position_id} open",
            filled_volume=position.volume,
            position_id=position.position_id,
        )

    def _find_working_order(
        self, gateway: BrokerGateway, learned_order_ticket: int = 0
    ) -> BrokerTruth | None:
        matches = []
        for order in gateway.orders(None):
            expected_order = self._current.order_ticket or learned_order_ticket
            exact = bool(
                (expected_order > 0 and order.ticket == expected_order)
                or self._comment_matches(order.comment)
            )
            if exact:
                matches.append(order)
        if len(matches) > 1:
            return self._ambiguous("WORKING_ORDER", "multiple orders matched one execution")
        if not matches:
            return None
        order = matches[0]
        if order.symbol != self._current.symbol:
            return self._ambiguous(
                "WORKING_ORDER", "exact working-order identity belongs to a different symbol"
            )
        return BrokerTruth(
            resolved=True,
            state=ExecState.ACCEPTED,
            terminal=False,
            source="WORKING_ORDER",
            detail=f"order {order.ticket} still live",
            order_ticket=order.ticket,
            position_id=order.position_id,
        )

    def _resolve_history_order(
        self,
        gateway: BrokerGateway,
        since: int,
        until: int,
        learned_order_ticket: int = 0,
    ) -> BrokerTruth | None:
        matches = []
        for order in gateway.history_orders(since, until, None):
            expected_order = self._current.order_ticket or learned_order_ticket
            exact = bool(
                (expected_order > 0 and order.ticket == expected_order)
                or self._comment_matches(order.comment)
            )
            if exact:
                matches.append(order)
        if len(matches) > 1:
            return self._ambiguous("HISTORY_ORDER", "multiple history orders matched")
        if not matches:
            return None

        order = matches[0]
        if order.symbol != self._current.symbol:
            return self._ambiguous(
                "HISTORY_ORDER", "exact history-order identity belongs to a different symbol"
            )
        state = order.state.upper()
        common = dict(
            resolved=True,
            source="HISTORY_ORDER",
            order_ticket=order.ticket,
            position_id=order.position_id,
        )
        if state == "FILLED":
            return BrokerTruth(
                **common,
                state=ExecState.FILLED,
                terminal=False,
                detail=f"order {order.ticket} filled",
                filled_volume=order.volume_initial,
            )
        if state == "PARTIAL":
            return BrokerTruth(
                **common,
                state=ExecState.PARTIALLY_FILLED,
                terminal=False,
                detail=f"order {order.ticket} partially filled",
                filled_volume=max(0.0, order.volume_initial - order.volume_current),
            )
        if state in ("CANCELED", "CANCELLED", "EXPIRED"):
            return BrokerTruth(
                **common,
                state=ExecState.CANCELLED,
                terminal=True,
                detail=f"order {order.ticket} cancelled/expired",
            )
        if state == "REJECTED":
            return BrokerTruth(
                **common,
                state=ExecState.REJECTED,
                terminal=True,
                detail=f"order {order.ticket} rejected",
            )
        return None

    def _resolve_from_deals(
        self, gateway: BrokerGateway, since: int, until: int
    ) -> BrokerTruth | None:
        # Exit deals created by a human, stop, target or broker intervention may
        # not retain the opening EA's magic. Fetch the bounded account history
        # and correlate only by exact ticket/position/comment links below.
        raw = list(gateway.history_deals(since, until, None))

        # Establish the execution's position identity only from exact links.
        position_ids: set[int] = set()
        if self._current.position_id > 0:
            position_ids.add(self._current.position_id)
        for deal in raw:
            exact_seed = self._deal_directly_matches_current(deal)
            if exact_seed and deal.position_id > 0:
                position_ids.add(deal.position_id)

        if len(position_ids) > 1:
            return self._ambiguous(
                "HISTORY_DEAL", "exact broker links resolve to multiple position ids"
            )

        # A netting position may accept later entries from a human or another
        # EA under the same position_id. Such an entry changes both volume and
        # ownership. It is not ours merely because the position is ours; only a
        # direct order/deal/comment link can admit an entry into this execution.
        foreign_entries = [
            deal
            for deal in raw
            if deal.position_id > 0
            and deal.position_id in position_ids
            and deal.entry in (0, DEAL_ENTRY_INOUT)
            and not self._deal_directly_matches_current(deal)
        ]
        if foreign_entries:
            return self._ambiguous(
                "HISTORY_DEAL",
                "position contains an entry without a direct execution link",
            )

        matched: list[DealInfo] = []
        for deal in raw:
            exact = (
                (self._current.deal_ticket > 0 and deal.ticket == self._current.deal_ticket)
                or (self._current.order_ticket > 0 and deal.order == self._current.order_ticket)
                or (deal.position_id > 0 and deal.position_id in position_ids)
                or self._comment_matches(deal.comment)
            )
            if exact:
                matched.append(deal)

        return self._truth_from_deals(matched, position_ids, source="HISTORY_DEAL")

    def _truth_from_deals(
        self,
        matched: list[DealInfo],
        position_ids: set[int] | None = None,
        *,
        source: str,
    ) -> BrokerTruth | None:
        """Reduce already-exact deals without inferring any missing fact."""
        if not matched:
            return None

        # History is expected to contain one row per deal ticket, but truth must
        # not depend on that courtesy. Identical duplicates are collapsed;
        # conflicting rows under one broker ticket are an explicit anomaly.
        unique: dict[int, DealInfo] = {}
        for deal in matched:
            if deal.ticket <= 0:
                return self._ambiguous(source, "exact deal has no broker ticket")
            previous = unique.get(deal.ticket)
            if previous is not None and previous != deal:
                return self._ambiguous(
                    source, "one broker deal ticket has conflicting facts"
                )
            unique[deal.ticket] = deal
        matched = list(unique.values())

        if any(deal.symbol != self._current.symbol for deal in matched):
            return self._ambiguous(
                source,
                "exact deal identity belongs to a different symbol",
                deals=tuple(matched),
            )
        known_entry_types = {0, DEAL_ENTRY_OUT, DEAL_ENTRY_INOUT, DEAL_ENTRY_OUT_BY}
        if any(deal.entry not in known_entry_types for deal in matched):
            return self._ambiguous(
                source,
                "exact deal has an unsupported entry classification",
                deals=tuple(matched),
            )
        if any(deal.volume <= 0.0 or deal.price <= 0.0 for deal in matched):
            return self._ambiguous(
                source,
                "exact trade deal has a non-positive volume or price",
                deals=tuple(matched),
            )

        position_ids = set(position_ids or ())
        position_ids.update(deal.position_id for deal in matched if deal.position_id > 0)
        if len(position_ids) > 1:
            return self._ambiguous(
                source,
                "exact deals resolve to multiple position ids",
                deals=tuple(matched),
            )
        matched.sort(key=lambda d: (d.time, d.ticket))
        if any(deal.entry == DEAL_ENTRY_INOUT for deal in matched):
            return self._ambiguous(
                source,
                "INOUT/reversal deal cannot be reduced to one entry and one outcome",
                deals=tuple(matched),
            )

        entries = [deal for deal in matched if deal.entry == 0]
        exits = [deal for deal in matched if deal.entry in (DEAL_ENTRY_OUT, DEAL_ENTRY_OUT_BY)]
        entry_order_ids = {deal.order for deal in entries if deal.order > 0}
        if self._current.order_ticket > 0:
            entry_order_ids.add(self._current.order_ticket)
        if len(entry_order_ids) > 1:
            return self._ambiguous(
                source,
                "exact entry deals disagree on opening order identity",
                deals=tuple(matched),
            )
        order_ticket = next(iter(entry_order_ids), 0)
        volume_in = sum(deal.volume for deal in entries)
        volume_out = sum(deal.volume for deal in exits)
        if (
            self._current.requested_volume > 0.0
            and volume_in > self._current.requested_volume + 1e-8
        ):
            return self._ambiguous(
                source,
                "exact entry volume exceeds the submitted request volume",
                deals=tuple(matched),
                order_ticket=order_ticket,
                position_id=next(iter(position_ids), 0),
            )
        filled = volume_in or self._current.filled_volume
        position_id = next(iter(position_ids), 0)

        entry_price = (
            sum(deal.price * deal.volume for deal in entries) / volume_in
            if volume_in > 0.0
            else 0.0
        )
        exit_price = (
            sum(deal.price * deal.volume for deal in exits) / volume_out
            if volume_out > 0.0
            else 0.0
        )
        # Every closing slice must state the same broker reason. Filtering out
        # an empty reason would turn [UNKNOWN, TP] into TP and create a win by
        # omission. Missing and mixed are explicit non-scorable dispositions.
        reasons = {
            (deal.reason or "").strip().upper() or "UNKNOWN" for deal in exits
        }
        close_reason = (
            next(iter(reasons))
            if len(reasons) == 1
            else ("MIXED" if reasons else "")
        )

        if filled > 0.0 and volume_out > filled + 1e-8:
            return self._ambiguous(
                source,
                "position exit volume exceeds this execution's exact entry volume",
                deals=tuple(matched),
                order_ticket=order_ticket,
                position_id=position_id,
            )

        truth = BrokerTruth(
            resolved=True,
            source=source,
            filled_volume=filled,
            closed_volume=volume_out,
            order_ticket=order_ticket,
            position_id=position_id,
            deals=tuple(matched),
            entry_price=entry_price,
            exit_price=exit_price,
            net_profit=sum(deal.net_profit for deal in matched),
            close_reason=close_reason,
            closed_at=max((deal.time for deal in exits), default=0),
        )
        if filled > 0.0 and volume_out + 1e-8 >= filled:
            truth.state = ExecState.COMPLETED
            truth.terminal = True
            truth.detail = f"opened {filled:.2f} and closed {volume_out:.2f}"
        else:
            truth.state = (
                ExecState.PARTIALLY_FILLED
                if filled + 1e-8 < self._current.requested_volume
                else ExecState.FILLED
            )
            truth.terminal = False
            truth.detail = f"filled {filled:.2f}, {max(0.0, filled - volume_out):.2f} still open"
        return truth

    def truth_from_persisted_deals(self, deals: list[DealInfo]) -> BrokerTruth:
        """Rebuild after a crash from broker facts already committed locally.

        These rows were admitted only after exact execution correlation. They
        are therefore evidence, not a cache guess, and can close the tiny crash
        window between persisting COMPLETED and persisting its outcome even if
        MT5 history is temporarily unavailable on restart.
        """
        truth = self._truth_from_deals(
            list(deals),
            {self._current.position_id} if self._current.position_id > 0 else set(),
            source="PERSISTED_BROKER_DEALS",
        )
        if (
            truth is not None
            and truth.terminal
            and truth.filled_volume + 1e-8 < self._current.requested_volume
        ):
            # Locally durable deals prove that the observed partial fill made a
            # round trip; they do not prove the server cancelled the unfilled
            # remainder. Only fresh live Order/Position reads can close that
            # question after restart.
            truth.state = ExecState.UNKNOWN
            truth.terminal = False
            truth.ambiguous = True
            truth.detail = (
                f"{truth.detail}; persisted deals close only an observed partial "
                "fill and cannot state the request remainder"
            )
        return truth or BrokerTruth(resolved=False)

    def resolve_from_broker(self, gateway: BrokerGateway, now: int) -> BrokerTruth:
        """Rebuild one coherent truth from every broker source.

        Deals are consulted before order disposition so an order marked FILLED
        cannot hide the later closing deals. Contradictory exact sources are an
        immediate UNKNOWN; silence merely waits for the fixed grace deadline.
        """
        since = self._current.created_at - 3600 if self._current.created_at > 0 else now - 86400
        until = now + 3600

        answers: dict[str, BrokerTruth | None] = {}
        failed: set[str] = set()

        def read(name: str, resolver) -> BrokerTruth | None:
            try:
                answer = resolver()
            except Exception as error:
                failed.add(name)
                self._journal.warn(
                    "BROKER_TRUTH_SOURCE_FAILED",
                    self._current.symbol,
                    f"{name} raised: {error}",
                    now,
                )
                answer = None
            answers[name] = answer
            return answer

        # Deals are read first deliberately. An exact entry deal can be the only
        # place the position/order identifiers survived a lost send response.
        # Pass those broker ids into the live readers in this same reconciliation
        # round instead of waiting for a later pass or relying on comments being
        # copied onto the position row.
        deals = read(
            "HISTORY_DEAL", lambda: self._resolve_from_deals(gateway, since, until)
        )
        learned_position_id = deals.position_id if deals is not None else 0
        learned_order_ticket = deals.order_ticket if deals is not None else 0
        position = read(
            "POSITION",
            lambda: self._find_open_position(gateway, learned_position_id),
        )
        working = read(
            "WORKING_ORDER",
            lambda: self._find_working_order(gateway, learned_order_ticket),
        )
        history = read(
            "HISTORY_ORDER",
            lambda: self._resolve_history_order(
                gateway, since, until, learned_order_ticket
            ),
        )

        for answer in answers.values():
            if answer is not None and answer.ambiguous:
                return answer

        # Independent exact links must converge on one broker position. A
        # correlation comment pointing at one live position while the exact
        # order/deal tickets point at another is a collision or broker anomaly,
        # never a fact to resolve by source priority.
        position_ids = {
            answer.position_id
            for answer in (deals, position, working, history)
            if answer is not None and answer.position_id > 0
        }
        if len(position_ids) > 1:
            return self._ambiguous(
                "BROKER_SOURCES",
                "exact broker sources disagree on position identity",
            )

        if deals is not None and deals.terminal:
            # A complete close of only the *observed* partial fill cannot prove
            # the unfilled remainder disappeared when either live source failed.
            # Full requested volume is different: there can be no remainder from
            # this order. Preserve the exact deals but keep the gate shut.
            if (
                deals.filled_volume + 1e-8 < self._current.requested_volume
                and ({"POSITION", "WORKING_ORDER"} & failed)
            ):
                return self._ambiguous(
                    "BROKER_SOURCES",
                    "observed partial fill is closed but live remainder state is unavailable",
                    deals=deals.deals,
                    order_ticket=deals.order_ticket,
                    position_id=deals.position_id,
                )
            if position is not None or working is not None:
                return self._ambiguous(
                    "BROKER_SOURCES",
                    "terminal deals contradict a live position/order",
                    deals=deals.deals,
                    order_ticket=deals.order_ticket,
                    position_id=deals.position_id,
                )
            return deals
        if position is not None:
            if deals is not None:
                expected_open = max(0.0, deals.filled_volume - deals.closed_volume)
                if (
                    deals.filled_volume > 0.0
                    and abs(position.filled_volume - expected_open) > 1e-8
                    and now - self._current.created_at
                    > self._config.execution.reconcile_grace_seconds
                ):
                    return self._ambiguous(
                        "BROKER_SOURCES",
                        "live position volume disagrees with exact execution deals",
                    )
                position.deals = deals.deals
                position.filled_volume = max(position.filled_volume, deals.filled_volume)
                position.closed_volume = deals.closed_volume
                position.entry_price = deals.entry_price
                position.exit_price = deals.exit_price
                position.net_profit = deals.net_profit
                position.close_reason = deals.close_reason
            return position
        if working is not None:
            if deals is not None:
                working.deals = deals.deals
                working.filled_volume = deals.filled_volume
                working.closed_volume = deals.closed_volume
                working.entry_price = deals.entry_price
                working.exit_price = deals.exit_price
                working.net_profit = deals.net_profit
                if deals.filled_volume > 0.0:
                    working.state = ExecState.PARTIALLY_FILLED
                    working.detail = (
                        f"order remains live after {deals.filled_volume:.2f} exact fill"
                    )
            return working
        if deals is not None:
            return deals
        if history is not None:
            # A terminal order disposition is only conclusive if deal history
            # answered successfully; otherwise a partial fill could be hidden.
            if history.terminal and "HISTORY_DEAL" in failed:
                return BrokerTruth(resolved=False)
            return history
        return BrokerTruth(resolved=False)

    # ------------------------------------------------------------- reconcile
    def _accept_truth(self, truth: BrokerTruth, now: int) -> BrokerTruth:
        self._current.state = truth.state
        # Belt and braces: even a resolver bug cannot mark a
        # not-actually-finished state as finished and reopen the gate.
        self._current.terminal = truth.terminal and may_be_auto_terminal(truth.state)
        self._current.message = truth.detail
        if truth.position_id > 0:
            self._current.position_id = truth.position_id
        if truth.order_ticket > 0:
            self._current.order_ticket = truth.order_ticket
        if truth.filled_volume > 0.0:
            # An open-position row states remaining volume. Never let a later
            # partial exit shrink the already established original fill.
            self._current.filled_volume = max(
                self._current.filled_volume, truth.filled_volume
            )
        self._current.closed_volume = max(self._current.closed_volume, truth.closed_volume)
        for deal in truth.deals:
            self._admit_correlated_deal(deal, now, mutate=False)
        self._journal.info(
            "RECONCILED",
            self._current.symbol,
            f"execution {self._current.execution_id} resolved as "
            f"{truth.state.name} via {truth.source} ({truth.detail})",
            now,
        )
        self._persist(now)
        return truth

    def reconcile_persisted_deals(
        self, deals: list[DealInfo], now: int
    ) -> BrokerTruth | None:
        """Apply exact locally persisted broker facts during restart."""
        if not self.has_unresolved() or not deals:
            return None
        truth = self.truth_from_persisted_deals(deals)
        return self._accept_truth(truth, now) if truth.resolved else truth

    def reconcile(self, gateway: BrokerGateway, now: int) -> BrokerTruth | None:
        """Rebuild the truth from the broker.

        Transaction events can be dropped entirely when the terminal's queue
        overflows, and the IPC link can drop outright, so nothing may depend on
        an event arriving.
        """
        if not self.has_unresolved():
            return None

        truth = self.resolve_from_broker(gateway, now)

        grace = self._config.execution.reconcile_grace_seconds
        if truth.resolved:
            # A working order or an open position is a complete statement of
            # current broker state, and a complete round trip/rejection is a
            # complete statement of terminal state. Historical evidence of an
            # entry *alone* is different: once the grace window has elapsed,
            # "filled but neither open nor closed" means at least one current
            # fact is missing. Leaving that state as FILLED forever would keep
            # the submit gate shut but never expose the operator's documented
            # acknowledgement path. Preserve every exact deal, then fail
            # closed as UNKNOWN so the discrepancy is explicit and actionable.
            current_fact = truth.source in ("POSITION", "WORKING_ORDER")
            inside_grace = now - self._current.created_at <= grace
            if truth.terminal or truth.ambiguous or current_fact or inside_grace:
                return self._accept_truth(truth, now)
            truth.state = ExecState.UNKNOWN
            truth.terminal = False
            truth.ambiguous = True
            truth.detail = (
                f"{truth.detail}; historical fill has no exact live "
                "position/order or complete exit after reconciliation grace"
            )
            return self._accept_truth(truth, now)

        # Not resolvable yet. Inside the grace period this is normal — the
        # server may simply not have answered.
        # The deadline is anchored to the persisted intent, not ``updated_at``.
        # Polling updates the latter; using it here renewed the grace period on
        # every pass and could keep an execution in RECONCILING forever.
        if now - self._current.created_at <= grace:
            self._current.state = ExecState.RECONCILING
            self._persist(now)
            return truth

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
        return truth

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
    def _deal_matches_current(self, deal: DealInfo) -> bool:
        """Whether a deal carries an exact identity for the current execution."""
        if not self._current.execution_id:
            return False
        direct = self._deal_directly_matches_current(deal)
        position_link = bool(
            self._current.position_id > 0
            and deal.position_id == self._current.position_id
        )
        # A broker/manual exit is legitimately linked by exact position id even
        # when it does not inherit the opening order's comment or magic. A new
        # IN under the same netting position is different: it changes ownership
        # and volume, so position id alone must never admit it as our fill.
        if deal.entry in (DEAL_ENTRY_OUT, DEAL_ENTRY_OUT_BY):
            return direct or position_link
        return direct

    def _admit_correlated_deal(
        self, deal: DealInfo, now: int, *, mutate: bool
    ) -> bool:
        exact_identity = bool(
            self._deal_directly_matches_current(deal)
            or (
                self._current.position_id > 0
                and deal.position_id == self._current.position_id
            )
        )
        if exact_identity and deal.symbol != self._current.symbol:
            # An exact ticket/position/comment pointing at another symbol is a
            # broker anomaly or corrupted response, not an unrelated event to
            # ignore. Surface it and retain the send lock.
            self._current.state = ExecState.UNKNOWN
            self._current.terminal = False
            self._current.message = "EXACT_IDENTITY_SYMBOL_CONFLICT"
            self._journal.error(
                "EXACT_IDENTITY_SYMBOL_CONFLICT",
                deal.symbol,
                f"deal {deal.ticket} exactly links to {self._current.execution_id} "
                f"but reports {deal.symbol} instead of {self._current.symbol}",
                now,
            )
            self._persist(now)
            return False

        position_only_entry = bool(
            deal.entry in (0, DEAL_ENTRY_INOUT)
            and self._current.position_id > 0
            and deal.position_id == self._current.position_id
            and not self._deal_directly_matches_current(deal)
        )
        if position_only_entry:
            # This is evidence of netting contamination, not this execution's
            # entry. Do not put it in the correlated ledger; keep the submit
            # gate shut and require the account to be inspected.
            self._current.state = ExecState.UNKNOWN
            self._current.terminal = False
            self._current.message = "FOREIGN_NETTING_ENTRY_REQUIRES_MANUAL_REVIEW"
            self._journal.error(
                "FOREIGN_NETTING_ENTRY",
                deal.symbol,
                f"deal {deal.ticket} entered position {deal.position_id} without "
                "an exact order/deal/comment link",
                now,
            )
            self._persist(now)
            return False

        # Correlate BEFORE durable admission. The old order recorded unrelated
        # same-symbol deals in this execution's evidence table and only then
        # discovered they should not move state.
        if not self._deal_matches_current(deal):
            self._journal.debug(
                "UNRELATED_DEAL_IGNORED",
                deal.symbol,
                f"deal {deal.ticket} has no exact link to {self._current.execution_id}",
                now,
            )
            return False

        admitted = self._ledger.admit(
            deal.ticket,
            execution_id=self._current.execution_id,
            symbol=deal.symbol,
            entry=deal.entry,
            volume=deal.volume,
            price=deal.price,
            net_profit=deal.net_profit,
            recorded_at=now,
            order_ticket=deal.order,
            position_id=deal.position_id,
            broker_time=deal.time,
            reason=deal.reason,
            comment=deal.comment,
        )
        if not admitted:
            return False
        if not mutate:
            return True

        if deal.entry == DEAL_ENTRY_INOUT:
            self._current.state = ExecState.UNKNOWN
            self._current.terminal = False
            self._current.message = "INOUT_DEAL_REQUIRES_MANUAL_REVIEW"
            self._persist(now)
            return True

        if deal.entry == 0:
            if self._current.order_ticket <= 0 and deal.order > 0:
                self._current.order_ticket = deal.order
            if deal.position_id > 0:
                self._current.position_id = deal.position_id
            self._current.filled_volume += deal.volume
            self._current.state = (
                ExecState.FILLED
                if self._current.filled_volume + 1e-8 >= self._current.requested_volume
                else ExecState.PARTIALLY_FILLED
            )
        elif deal.entry in (DEAL_ENTRY_OUT, DEAL_ENTRY_OUT_BY):
            if deal.position_id > 0:
                self._current.position_id = deal.position_id
            self._current.closed_volume += deal.volume
            if (
                self._current.filled_volume > 0.0
                and self._current.closed_volume + 1e-8 >= self._current.filled_volume
            ):
                self._current.state = ExecState.COMPLETED
                self._current.terminal = True
            else:
                # A partial exit is still an open risk, never a completed trade.
                self._current.state = ExecState.POSITION_ACTIVE
                self._current.terminal = False
        self._persist(now)
        return True

    def apply_deal(self, deal: DealInfo, now: int) -> bool:
        """Fold one deal into execution state, at most once.

        Returns True when the deal was admitted. A replayed ticket is refused
        here, before it can touch ``filled_volume`` — the defect that made the
        MQL5 ledger's idempotency decorative was recording the ticket and then
        mutating state regardless.
        """
        admitted = self._admit_correlated_deal(deal, now, mutate=True)
        if not admitted:
            self._journal.debug(
                "DEAL_REPLAY_OR_UNRELATED",
                deal.symbol,
                f"deal {deal.ticket} was already applied or was not correlated",
                now,
            )
        return admitted
